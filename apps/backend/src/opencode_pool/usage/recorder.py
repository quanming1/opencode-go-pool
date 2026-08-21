"""用量记录器（C2 FR1-FR4）。

在每次转发完成后记录一条用量事件到 store（与 B4 同一 SQLite），
并提供聚合统计查询。记录失败不影响转发主路径。

C4 之后：switch_history / kind_label 已删除，状态类事件统一走 events 模块；
usage_events 仅保留为统计投影（PRD-C4 §3）。
G8 之后：FAST_MODE（fast_mode=True）下成功请求不落库，只更新固定上限
内存聚合（metrics/fast.py FastMetrics）；stats 输出结构与 normal 一致，
并带 mode 字段标注数据口径（PRD-G8）。
"""

import logging
import threading
import time as _time

from opencode_pool.store.sqlite_store import AccountStore

logger = logging.getLogger("opencode_pool.usage")

# G7：/api/stats 聚合结果 TTL 缓存（秒）——监控台 10s 轮询命中缓存，
# 聚合查询不再重复执行（调用方 asyncio.to_thread 移出事件循环）
STATS_CACHE_TTL_SECONDS = 3.0

# G8：FAST_MODE 下 summary.event_counts 的默认结构（与 sqlite_store.events_summary 一致）
_DEFAULT_EVENT_COUNTS = {
    "key_switch": 0,
    "key_cooldown_started": 0,
    "key_disabled": 0,
    "all_keys_unavailable": 0,
    "all_keys_invalid": 0,
}


class UsageRecorder:
    """把转发用量写入 store 并暴露统计查询。

    G7：构造可选 writer（SQLiteWriter）——非 None 时 record 仅入队（零阻塞），
    由单写线程异步落库；无 writer（默认）保持同步直写（测试/独立使用）。
    G8：构造可选 fast_mode——开启时 record 仅更新 FastMetrics（内存聚合，
    零 IO 零 JSON），stats 从内存快照生成；duration_ms/protocol 仅用于
    fast 聚合（save_usage 无这两列，normal 模式忽略）。
    """

    def __init__(
        self,
        store: AccountStore,
        writer: object | None = None,
        fast_mode: bool = False,
    ) -> None:
        self._store = store
        # G7：异步落库队列（需提供 submit(fn, *args)；None = 同步直写）
        self._writer = writer
        # G8：极致性能模式（成功请求只进内存聚合，见 PRD-G8 FR4）
        self._fast_mode = fast_mode
        self._metrics = None
        if fast_mode:
            from opencode_pool.metrics.fast import FastMetrics

            self._metrics = FastMetrics()
        self._stats_cache: tuple[float, tuple[int, dict]] | None = None
        self._stats_cache_lock = threading.Lock()

    def record(
        self,
        account_id: str,
        kind: str,
        error_type: str | None = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        model: str | None = None,
        duration_ms: int = 0,
        protocol: str = "",
    ) -> None:
        """记录一条用量事件（ts 用当前 UTC 时间）。

        duration_ms/protocol 仅 FAST_MODE 聚合使用（usage_events 无这两列，
        E4 的耗时/协议分布来自 events 表；fast 模式成功事件不落库，
        故由本参数补进内存聚合）。
        """
        try:
            import datetime as _dt

            ts = _dt.datetime.now(_dt.UTC).isoformat()
            if self._fast_mode:
                # G8：只更新固定上限内存聚合——零 IO / 零 JSON / 零入队
                self._metrics.update(
                    ts=ts,
                    account_id=account_id,
                    model=model,
                    success=kind == "success",
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    duration_ms=duration_ms,
                    protocol=protocol,
                    error_type=error_type,
                )
                return
            if self._writer is not None:
                # G7：异步落库——仅入队，写线程执行；参数不可变，闭包安全
                # G8：成功快照标记 droppable（写队列满载时可被驱逐重建）
                self._writer.submit(
                    self._store.save_usage,
                    ts,
                    account_id,
                    kind,
                    error_type,
                    prompt_tokens,
                    completion_tokens,
                    model,
                    droppable=kind == "success",
                )
                return
            self._store.save_usage(
                ts=ts,
                account_id=account_id,
                kind=kind,
                error_type=error_type,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                model=model,
            )
        except Exception:  # noqa: BLE001 - 统计失败不拖垮转发
            logger.warning("[usage] 记录用量失败（忽略）")

    def stats(self, hours: int = 24) -> dict:
        if self._fast_mode:
            return self._fast_stats(hours)
        return self._cached_or_fetch(hours)

    def _fast_stats(self, hours: int) -> dict:
        """FAST_MODE：纯内存实时快照（µs 级，不走 TTL 缓存）+ DB 状态事件计数。"""
        data = self._metrics.snapshot(hours)
        data["mode"] = "fast"
        try:
            event_counts = self._store.events_summary().get("event_counts", {})
        except Exception:  # noqa: BLE001 - 补充维度失败不拖垮统计
            event_counts = {}
        data["summary"]["event_counts"] = {**_DEFAULT_EVENT_COUNTS, **event_counts}
        return data

    def _cached_or_fetch(self, hours: int) -> dict:
        """3 秒 TTL 缓存按 hours 区分；命中直接返回，未命中聚合 + 合并 summary。"""
        now = _time.monotonic()
        with self._stats_cache_lock:
            if (
                self._stats_cache is not None
                and now - self._stats_cache[0] < STATS_CACHE_TTL_SECONDS
                and self._stats_cache[1][0] == hours
            ):
                return self._stats_cache[1][1]
        data = self._store.aggregate_usage(hours=hours)
        # E4：合并事件派生聚合（耗时/协议分布/状态事件计数）；失败降级为默认结构
        try:
            data["summary"] = self._store.events_summary()
        except Exception:  # noqa: BLE001 - 补充维度失败不拖垮统计
            data["summary"] = {
                "window": 500,
                "duration_ms": {"avg": None, "p95": None, "max": None},
                "protocol": [],
                "event_counts": {
                    "key_switch": 0,
                    "key_cooldown_started": 0,
                    "key_disabled": 0,
                    "all_keys_unavailable": 0,
                    "all_keys_invalid": 0,
                },
            }
        with self._stats_cache_lock:
            self._stats_cache = (_time.monotonic(), (hours, data))
        data["mode"] = "normal"
        return data