"""用量记录器（C2 FR1-FR4）。

在每次转发完成后记录一条用量事件到 store（与 B4 同一 SQLite），
并提供聚合统计查询。记录失败不影响转发主路径。

C4 之后：switch_history / kind_label 已删除，状态类事件统一走 events 模块；
usage_events 仅保留为统计投影（PRD-C4 §3）。
"""

import logging

from opencode_pool.store.sqlite_store import AccountStore

logger = logging.getLogger("opencode_pool.usage")


class UsageRecorder:
    """把转发用量写入 store 并暴露统计查询。"""

    def __init__(self, store: AccountStore) -> None:
        self._store = store

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
        return data