"""用量记录器（C2 FR1-FR4）。

在每次转发完成后记录一条用量事件到 store（与 B4 同一 SQLite），
并提供聚合统计与切换历史查询。记录失败不影响转发主路径。
"""

import logging

from opencode_pool.store.sqlite_store import AccountStore

logger = logging.getLogger("opencode_pool.usage")

# kind -> 中文语义（PRD-C2 FR4）
KIND_LABELS = {
    "quota": "额度限制",
    "auth": "鉴权失败",
    "server": "上游错误",
    "network": "网络错误",
    "bad_request": "请求无效",
    "recover": "恢复",
    "disable": "禁用",
    "enable": "启用",
    "clear": "清除",
    "auto_disable": "自动禁用",
    "success": "成功",
    "error": "失败",
}


def kind_label(kind: str) -> str:
    return KIND_LABELS.get(kind, kind)


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
        return self._store.aggregate_usage(hours=hours)

    def switch_history(self, limit: int = 50) -> list[dict]:
        """切换历史（新→旧），附中文 kind_label。"""
        events = self._store.load_history(limit=limit)
        return [
            {
                "ts": e["ts"],
                "account_id": e["account_id"],
                "kind": e["kind"],
                "reason": e["reason"],
                "kind_label": kind_label(e["kind"]),
            }
            for e in events
        ]
