"""极致性能模式的内存聚合器（G8 FR2）。

FAST_MODE 下成功请求不落 SQLite、不构造事件 JSON，只更新这里的
固定上限内存聚合；`snapshot(hours)` 输出与 `aggregate_usage +
events_summary(耗时/协议部分)` 兼容的结构，保证 /api/stats 字段契约不变。

有界性（内存硬上限）：
- 小时桶滚动窗口：最多 `FAST_WINDOW_HOURS` 桶，超窗丢弃最旧桶；
- 每桶 duration 样本：最多 `FAST_DURATION_SAMPLES` 条，超出丢最旧（p95 为近似值）；
- per_account / per_account_models 键集合受账号数与上游模型清单约束，
  模型集有限（YAML 锚点 14 项），实际有界。

线程安全：record 由事件循环线程调用，snapshot 由 asyncio.to_thread
工作线程调用（/api/stats），用 Lock 串行化。
"""

import math
import threading
from collections import Counter, deque

# 聚合窗口：保留最近 168 小时（7 天，与 /api/stats?hours 上限一致）
FAST_WINDOW_HOURS = 168
# 每桶耗时样本上限（p95/max 近似值；超出丢最旧）
FAST_DURATION_SAMPLES = 500


class _AccountAgg:
    """单账号聚合（每小时内）。"""

    __slots__ = ("request_count", "success_count", "prompt_tokens", "completion_tokens")

    def __init__(self) -> None:
        self.request_count = 0
        self.success_count = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0


class _ModelAgg(_AccountAgg):
    """账号 x 模型聚合（继承 _AccountAgg 的计数语义）。"""


class _HourBucket:
    """单小时桶聚合。"""

    __slots__ = (
        "request_count",
        "success_count",
        "prompt_tokens",
        "completion_tokens",
        "durations",
        "protocol",
        "accounts",
        "models",
    )

    def __init__(self) -> None:
        self.request_count = 0
        self.success_count = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        # 耗时样本（有界，见 FAST_DURATION_SAMPLES）
        self.durations: deque[float] = deque(maxlen=FAST_DURATION_SAMPLES)
        self.protocol: Counter[str] = Counter()
        self.accounts: dict[str, _AccountAgg] = {}
        self.models: dict[tuple[str, str], _ModelAgg] = {}


class FastMetrics:
    """FAST_MODE 的统计唯一数据源（内存聚合，永不落盘）。

    update() 单次 O(1)；snapshot(hours) 生成 stats 兼容结构（纯内存，
    微秒级，不走 3s TTL 缓存——FAST_MODE 下实时即最新）。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # 小时桶：key = 小时槽（%Y-%m-%dT%H:00:00，UTC ISO 前缀）
        self._buckets: dict[str, _HourBucket] = {}
        # 全局错误类型分布（E4 stats.error_types 契约）
        self._error_types: Counter[str] = Counter()

    # ---- 记录（事件循环线程） ----

    def update(
        self,
        *,
        ts: str,
        account_id: str,
        model: str | None,
        success: bool,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        duration_ms: int = 0,
        protocol: str = "",
        error_type: str | None = None,
    ) -> None:
        """一次请求的内存聚合：O(1) 更新（成功/失败都计数）。"""
        # 小时槽：ISO 时间串 "(YYYY-MM-DDTHH:MM:SS...)" 截前 13 位 + ":00:00"
        hour = f"{ts[:13]}:00:00"
        with self._lock:
            bucket = self._buckets.get(hour)
            if bucket is None:
                bucket = _HourBucket()
                self._buckets[hour] = bucket
                self._trim_window()
            bucket.request_count += 1
            if success:
                bucket.success_count += 1
            bucket.prompt_tokens += prompt_tokens
            bucket.completion_tokens += completion_tokens
            if duration_ms > 0:
                bucket.durations.append(float(duration_ms))
            if protocol:
                bucket.protocol[protocol] += 1
            acc = bucket.accounts.get(account_id)
            if acc is None:
                acc = _AccountAgg()
                bucket.accounts[account_id] = acc
            acc.request_count += 1
            if success:
                acc.success_count += 1
            acc.prompt_tokens += prompt_tokens
            acc.completion_tokens += completion_tokens
            if model:
                key = (account_id, model)
                macc = bucket.models.get(key)
                if macc is None:
                    macc = _ModelAgg()
                    bucket.models[key] = macc
                macc.request_count += 1
                if success:
                    macc.success_count += 1
                macc.prompt_tokens += prompt_tokens
                macc.completion_tokens += completion_tokens
            if error_type:
                self._error_types[error_type] += 1

    def _trim_window(self) -> None:
        """超过窗口上限时丢弃最旧桶（有界保证）。"""
        while len(self._buckets) > FAST_WINDOW_HOURS:
            oldest = min(self._buckets)
            del self._buckets[oldest]

    # ---- 查询（asyncio.to_thread 工作线程） ----

    def snapshot(self, hours: int = 24) -> dict:
        """生成与 aggregate_usage 兼容的 stats 结构（含 summary 耗时/协议部分）。"""
        with self._lock:
            buckets = dict(self._buckets)
            error_types = dict(self._error_types)

        # 取最近 hours 个桶（时间从新到旧）
        ordered = sorted(buckets, reverse=True)[:hours]
        totals = {
            "request_count": 0,
            "success_count": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
        }
        total_durations: deque[float] = deque(maxlen=FAST_DURATION_SAMPLES)
        protocol_total: Counter[str] = Counter()
        per_account: dict[str, dict] = {}
        per_account_models: dict[tuple[str, str], dict] = {}
        bucket_rows: list[dict] = []

        for hour in ordered:  # 新 → 旧
            b = buckets[hour]
            totals["request_count"] += b.request_count
            totals["success_count"] += b.success_count
            totals["prompt_tokens"] += b.prompt_tokens
            totals["completion_tokens"] += b.completion_tokens
            total_durations.extend(b.durations)
            protocol_total.update(b.protocol)
            # per_account 合并
            for aid, a in b.accounts.items():
                agg = per_account.setdefault(aid, {
                    "account_id": aid,
                    "request_count": 0,
                    "success_count": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "error_count": 0,
                })
                agg["request_count"] += a.request_count
                agg["success_count"] += a.success_count
                agg["prompt_tokens"] += a.prompt_tokens
                agg["completion_tokens"] += a.completion_tokens
            # per_account_models 合并
            for (aid, model), m in b.models.items():
                magg = per_account_models.setdefault((aid, model), {
                    "account_id": aid,
                    "model": model,
                    "request_count": 0,
                    "success_count": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "error_count": 0,
                })
                magg["request_count"] += m.request_count
                magg["success_count"] += m.success_count
                magg["prompt_tokens"] += m.prompt_tokens
                magg["completion_tokens"] += m.completion_tokens
            bucket_rows.append({
                "hour": hour,
                "request_count": b.request_count,
                "success_count": b.success_count,
                "prompt_tokens": b.prompt_tokens,
                "completion_tokens": b.completion_tokens,
            })

        # error_count 由 request_count - success_count 推算
        for agg in per_account.values():
            agg["error_count"] = agg["request_count"] - agg["success_count"]
        for magg in per_account_models.values():
            magg["error_count"] = magg["request_count"] - magg["success_count"]

        success_count = totals["success_count"]
        total_count = totals["request_count"]
        success_rate = round(success_count / total_count, 4) if total_count else 1.0

        duration_ms = {
            "avg": None,
            "p95": None,
            "max": None,
        }
        if total_durations:
            samples = sorted(total_durations)
            duration_ms["avg"] = round(sum(samples) / len(samples), 2)
            duration_ms["max"] = round(samples[-1], 2)
            if len(samples) >= 2:
                # 与 sqlite_store.events_summary 同口径：ceil(n*0.95)-1 索引
                idx = max(0, math.ceil(len(samples) * 0.95) - 1)
                duration_ms["p95"] = round(samples[idx], 2)

        return {
            "totals": {
                **totals,
                "error_count": max(total_count - success_count, 0),
                "success_rate": success_rate,
            },
            "per_account": sorted(
                per_account.values(), key=lambda x: x["request_count"], reverse=True
            ),
            "per_account_models": sorted(
                per_account_models.values(),
                key=lambda x: x["request_count"],
                reverse=True,
            ),
            "buckets": bucket_rows,
            "error_types": [
                {"type": t, "count": c}
                for t, c in sorted(error_types.items(), key=lambda x: x[1], reverse=True)
            ],
            "summary": {
                "window": len(ordered),
                "duration_ms": duration_ms,
                "protocol": [
                    {"name": p, "count": c}
                    for p, c in protocol_total.most_common()
                ],
                # event_counts 由调用方从 store.events_summary() 合并（DB 状态事件）
                "event_counts": {},
            },
        }