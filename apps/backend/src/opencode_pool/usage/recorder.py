"""用量记录器（C2 FR1-FR4）。

在每次转发完成后记录一条用量事件到 store（与 B4 同一 SQLite），
并提供聚合统计查询。记录失败不影响转发主路径。

C4 之后：switch_history / kind_label 已删除，状态类事件统一走 events 模块；
usage_events 仅保留为统计投影（PRD-C4 §3）。
"""

import logging
import threading
import time as _time

from opencode_pool.store.sqlite_store import AccountStore

logger = logging.getLogger("opencode_pool.usage")

# G7：/api/stats 聚合结果 TTL 缓存（秒）——监控台 10s 轮询命中缓存，
# 聚合查询不再重复执行（调用方 asyncio.to_thread 移出事件循环）
STATS_CACHE_TTL_SECONDS = 3.0


class UsageRecorder:
    """把转发用量写入 store 并暴露统计查询。

    G7：构造可选 writer（SQLiteWriter）——非 None 时 record 仅入队（零阻塞），
    由单写线程异步落库；无 writer（默认）保持同步直写（测试/独立使用）。
    """

    def __init__(self, store: AccountStore, writer: object | None = None) -> None:
        self._store = store
        # G7：异步落库队列（需提供 submit(fn, *args)；None = 同步直写）
        self._writer = writer
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
    ) -> None:
        """记录一条用量事件（ts 用当前 UTC 时间）。"""
        try:
            import datetime as _dt

            ts = _dt.datetime.now(_dt.UTC).isoformat()
            if self._writer is not None:
                # G7：异步落库——仅入队，写线程执行；参数不可变，闭包安全
                self._writer.submit(
                    self._store.save_usage,
                    ts,
                    account_id,
                    kind,
                    error_type,
                    prompt_tokens,
                    completion_tokens,
                    model,
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
        data = self._cached_or_fetch(hours)
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
        return data