"""日志概览服务（D1 FR3/FR4）：当前活跃 Key + 剩余时长推测。

只读能力，不触碰转发主路径；任何上游/数据缺失降级为 None/空。
"""

import logging

from opencode_pool.events.recorder import EventType

logger = logging.getLogger("opencode_pool.logs")

# OpenCode Go 滚动窗口（5 小时）单账号约 2000 次请求（与 store.usage_limit 同源约定）
WINDOW_REQUESTS_PER_ACCOUNT = 2000

# 从最近 N 条 request 事件里找最近成功请求作为"当前活跃 Key"
ACTIVE_SCAN_LIMIT = 500


class LogsOverview:
    """基于 store 与事件记录器计算日志概览。"""

    def __init__(self, store: object, event_recorder: object | None = None) -> None:
        self._store = store
        self._recorder = event_recorder

    def current_active(self) -> dict | None:
        """最近成功请求使用的账号（新→旧扫 request 事件），无则 None。"""
        if self._recorder is None:
            return None
        try:
            events = self._recorder.query(
                limit=ACTIVE_SCAN_LIMIT, types=[EventType.REQUEST.value]
            )
        except Exception:  # noqa: BLE001 - 概览失败降级
            logger.warning("[logs] 查询 request 事件失败（活跃 Key 降级 None）")
            return None
        for event in events:
            data = event.get("data") or {}
            if data.get("success") is True and data.get("account_id"):
                return {
                    "account_id": data["account_id"],
                    "last_success_at": event.get("time"),
                }
        return None

    def rate(self, minutes: int = 60) -> dict:
        """最近窗口请求/token 速率（store 口径）。"""
        try:
            rate = self._store.recent_usage_rate(minutes=minutes)
        except Exception:  # noqa: BLE001
            logger.warning("[logs] 统计请求速率失败（降级空）")
            rate = {
                "minutes": minutes,
                "requests": 0,
                "requests_per_minute": 0.0,
                "tokens": 0,
                "tokens_per_hour": 0,
            }
        return rate

    def usage_remaining(self, quota: dict | None, rate: dict) -> dict | None:
        """按滚动窗口均值百分比 + 本地请求速率推算剩余可用时长。

        估算口径（非账单保证）：滚动窗口单账号约 2000 次请求；
        池剩余请求次数 = (1 - rolling_avg_percent/100) × 2000 × 可用账号数。
        """
        if quota is None:
            return None
        summary = (quota.get("summary") or {}) if isinstance(quota, dict) else {}
        percent = summary.get("rolling_avg_percent")
        accounts = summary.get("total_accounts", 0)
        if not isinstance(percent, (int, float)) or accounts <= 0:
            return None
        requests_left = round((1 - percent / 100) * WINDOW_REQUESTS_PER_ACCOUNT * accounts)
        rps = float(rate.get("requests_per_minute") or 0)
        if rps <= 0:
            return None
        hours_left = round(requests_left / (rps * 60), 1)
        return {
            "estimated_requests_left": requests_left,
            "estimated_hours_left": hours_left,
            "basis": "rolling_percent_and_local_rate",
            "note": "估算口径：滚动窗口单账号约 2000 次，按当前速率线性推算",
        }

    def overview(self, quota: dict | None = None) -> dict:
        """组装日志概览。"""
        rate = self.rate()
        return {
            "current_active": self.current_active(),
            "rate": {
                "minutes": rate.get("minutes", 60),
                "requests_per_minute": rate.get("requests_per_minute", 0.0),
                "tokens_per_hour": rate.get("tokens_per_hour", 0),
            },
            "usage_remaining": self.usage_remaining(quota, rate),
        }
