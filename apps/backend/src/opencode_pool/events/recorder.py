"""统一事件记录器（C4）：type/data/meta/time 契约组装与落库。

统一事件契约（PRD-C4 §2）：
    {"type": ..., "data": {...}, "meta": {...}, "time": <UTC ISO-8601>}

- `type`：机器可筛选的事件类型（EventType 枚举）；
- `data`：事件业务内容；
- `meta`：公共上下文（source/request_id/route 等；schema_version 自动补齐）；
- `time`：事件发生时间（UTC）。

所有失败一律降级（不抛），保证不影响转发主路径（AC7）。
"""

import datetime as _dt
import json
import logging
from enum import StrEnum

logger = logging.getLogger("opencode_pool.events")

# 事件契约 schema 版本（meta.schema_version，迁移数据同版本）
SCHEMA_VERSION = 1


class EventType(StrEnum):
    """统一事件类型（PRD-C4 §2.1）。"""

    REQUEST = "request"
    KEY_COOLDOWN_STARTED = "key_cooldown_started"
    KEY_COOLDOWN_COMPLETED = "key_cooldown_completed"
    KEY_SWITCH = "key_switch"
    ALL_KEYS_INVALID = "all_keys_invalid"
    ALL_KEYS_UNAVAILABLE = "all_keys_unavailable"
    KEY_DISABLED = "key_disabled"
    KEY_ENABLED = "key_enabled"
    KEY_COOLDOWN_CLEARED = "key_cooldown_cleared"
    GATEWAY_KEY_CREATED = "gateway_key_created"
    GATEWAY_KEY_REVOKED = "gateway_key_revoked"


def _dumps(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


class EventRecorder:
    """组装统一事件并落库；store 不可用/失败一律降级。"""

    def __init__(self, store: object | None = None) -> None:
        # store 需提供 save_event(type_, event_time, data_json, meta_json)
        # 与 query_events(limit, types)（AccountStore 实现，duck-typing）。
        self._store = store

    def record(
        self,
        type_: str,
        data: dict,
        meta: dict | None = None,
    ) -> None:
        """记录一条事件（time=UTC ISO-8601；meta 自动补 schema_version）。"""
        event = {
            "type": str(type_),
            "data": data if data else {},
            "meta": {"schema_version": SCHEMA_VERSION, **(meta or {})},
            "time": _dt.datetime.now(_dt.UTC).isoformat(),
        }
        if self._store is None:
            return
        try:
            self._store.save_event(
                type_=event["type"],
                event_time=event["time"],
                data_json=_dumps(event["data"]),
                meta_json=_dumps(event["meta"]),
            )
        except Exception:  # noqa: BLE001 - 事件落库失败不拖垮主路径
            logger.warning("[events] 记录 %s 事件失败（降级忽略）", event["type"])

    def query(
        self,
        limit: int = 100,
        types: list[str] | None = None,
        offset: int = 0,
    ) -> list[dict]:
        """统一事件列表（新→旧）；每项严格含 type/data/meta/time。"""
        if self._store is None:
            return []
        try:
            rows = self._store.query_events(limit=limit, types=types, offset=offset)
        except Exception:  # noqa: BLE001 - 查询失败降级为空
            logger.warning("[events] 查询事件失败（降级为空）")
            return []
        return [
            {
                "type": r["type"],
                "data": r["data"],
                "meta": r["meta"],
                "time": r["event_time"],
            }
            for r in rows
        ]

    def count(self, types: list[str] | None = None) -> int:
        """事件总数（支持 type 白名单），供分页 has_more 判断；失败降级 0。"""
        if self._store is None:
            return 0
        try:
            return int(self._store.count_events(types=types))
        except Exception:  # noqa: BLE001 - 统计失败降级 0
            logger.warning("[events] 统计事件数失败（降级 0）")
            return 0