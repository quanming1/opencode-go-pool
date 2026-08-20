"""额度查询服务（C5 FR1/FR2/FR4）。

对账号池内所有 enabled 账号并发调用官方额度接口：

    GET {account.base_url}/usage   Authorization: Bearer <账号密钥>

返回 rolling/weekly/monthly 三窗口的已用百分比与重置倒计时。
设计要点（PRD-C5 §3.1）：
- TTL 缓存（默认 60s）+ asyncio.Lock 防击穿——缓存过期时只放一个请求打上游；
- 单账号失败（网络/4xx/解析异常）降级为 quota=null + error 摘要，不影响其他账号；
- 响应与日志绝不包含密钥。
"""

import asyncio
import datetime as _dt
import logging
import math
from typing import Any

import httpx

from opencode_pool.accounts.models import Account
from opencode_pool.accounts.pool import AccountPool

logger = logging.getLogger("opencode_pool.quota")
# 三窗口名（与上游 usage 响应键一致）
_WINDOWS = ("rolling", "weekly", "monthly")
# OpenCode Go 计划单账号窗口上限（美元）：仅用于汇总展示的近似折算，不代表账单。
QUOTA_LIMITS_USD = {"rolling": 12, "weekly": 30, "monthly": 60}

DEFAULT_CACHE_TTL_SECONDS = 60
DEFAULT_TIMEOUT_SECONDS = 10.0


def _now_utc() -> _dt.datetime:
    return _dt.datetime.now(_dt.UTC)


def _parse_window(raw: Any, now: _dt.datetime) -> dict | None:
    """解析单窗口 {status, percent, resetsAt} → 对外结构（含倒计时秒数）。

    字段缺失/类型不符一律返回 None（整个账号降级为未知，PRD FR1 容错）。
    """
    if not isinstance(raw, dict):
        return None

    status = raw.get("status")
    percent = raw.get("percent")
    resets_at = raw.get("resetsAt")
    if not isinstance(status, str) or isinstance(percent, bool):
        return None
    if not isinstance(percent, (int, float)) or not math.isfinite(float(percent)):
        return None
    if percent < 0 or percent > 100:
        return None
    if not isinstance(resets_at, str):
        return None

    try:
        expires = _dt.datetime.fromisoformat(resets_at.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=_dt.UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=_dt.UTC)

    return {
        "status": status,
        "percent": int(percent),
        "resets_at": resets_at,
        "resets_in_seconds": max(0, int((expires - now).total_seconds())),
    }


class QuotaService:
    """并发查询账号额度，带 TTL 缓存与降级。"""

    def __init__(
        self,
        pool: AccountPool,
        client: httpx.AsyncClient | None = None,
        cache_ttl: int = DEFAULT_CACHE_TTL_SECONDS,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        upstream_base_url: str = "",
        now: Any = _now_utc,
    ) -> None:
        self._pool = pool
        self._client = client
        self._cache_ttl = max(0, int(cache_ttl))
        self._timeout = timeout
        self._upstream_base_url = upstream_base_url
        self._now = now
        self._lock = asyncio.Lock()
        self._cache: dict | None = None  # {accounts, summary, fetched_at}
        # 未注入 client 时懒创建的自有连接（整个服务复用，避免每账号新建连接）
        self._own_client: httpx.AsyncClient | None = None

    async def fetch(self, force: bool = False) -> dict:
        """返回 {accounts, summary, fetched_at, cached}（PRD-C5 §4）。"""
        if not force and self._cache_fresh():
            return {**self._cache, "cached": True}

        async with self._lock:
            # 拿到锁后二次检查：等锁期间别的请求可能已刷新缓存
            if not force and self._cache_fresh():
                return {**self._cache, "cached": True}
            if self._client is None and self._own_client is None:
                self._own_client = httpx.AsyncClient(timeout=self._timeout)

            accounts = [a for a in self._pool.get_all() if a.enabled]
            results = await asyncio.gather(*(self._fetch_one(a) for a in accounts))
            fetched_at = self._now().isoformat()
            data = {
                "accounts": results,
                "summary": self._summarize(len(accounts), results),
                "fetched_at": fetched_at,
            }
            self._cache = data
            return {**data, "cached": False}

    async def close(self) -> None:
        """关闭服务内部创建的 HTTP 客户端；注入的 client 由调用方管理。"""
        if self._own_client is not None:
            await self._own_client.aclose()
            self._own_client = None

    def _cache_fresh(self) -> bool:
        if self._cache is None:
            return False
        try:
            fetched = _dt.datetime.fromisoformat(self._cache["fetched_at"])
        except (KeyError, TypeError, ValueError):
            return False
        current = self._now()
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=_dt.UTC)
        if current.tzinfo is None:
            current = current.replace(tzinfo=_dt.UTC)
        return (current - fetched).total_seconds() < self._cache_ttl

    def _usage_url(self, account: Account) -> str:
        if account.base_url:
            base = account.base_url.rstrip("/")
        else:
            base = self._upstream_base_url.rstrip("/")
        return f"{base}/usage"

    async def _fetch_one(self, account: Account) -> dict:
        """查单账号额度；任何失败降级为 {account_id, quota: None, error}。"""
        client = self._client or self._own_client
        assert client is not None  # fetch() 已保证（锁内初始化）
        try:
            resp = await client.get(
                self._usage_url(account),
                headers={"Authorization": f"Bearer {account.api_key}"},
            )
        except httpx.HTTPError as exc:
            logger.warning("[quota] %s 额度查询网络失败: %s", account.id, type(exc).__name__)
            return {"account_id": account.id, "quota": None, "error": type(exc).__name__}

        if resp.status_code != 200:
            logger.warning("[quota] %s 额度查询返回 http %d", account.id, resp.status_code)
            return {
                "account_id": account.id,
                "quota": None,
                "error": f"http {resp.status_code}",
            }
        try:
            body = resp.json()
        except ValueError:
            return {"account_id": account.id, "quota": None, "error": "invalid json"}

        usage = body.get("usage") if isinstance(body, dict) else None
        if not isinstance(usage, dict):
            return {"account_id": account.id, "quota": None, "error": "missing usage"}

        now = self._now()
        windows = {window: _parse_window(usage.get(window), now) for window in _WINDOWS}
        if any(window is None for window in windows.values()):
            return {"account_id": account.id, "quota": None, "error": "malformed usage"}
        return {"account_id": account.id, "quota": windows, "error": None}

    @staticmethod
    def _summarize(total_accounts: int, results: list[dict]) -> dict:
        """全池汇总（PRD-C5 §4 summary）：均值只统计查询成功的账号。"""
        ok = [result["quota"] for result in results if result["quota"] is not None]

        def avg(window: str) -> int:
            if not ok:
                return 0
            return round(sum(quota[window]["percent"] for quota in ok) / len(ok))
        def estimated_used(window: str) -> int:
            return round(
                sum(
                    quota[window]["percent"] * QUOTA_LIMITS_USD[window] / 100
                    for quota in ok
                )
            )

        return {
            "total_accounts": total_accounts,
            "queried": len(results),
            "ok_accounts": len(ok),
            "rolling_available": sum(
                1 for quota in ok if quota["rolling"]["status"] == "ok"
            ),
            "rolling_avg_percent": avg("rolling"),
            "weekly_avg_percent": avg("weekly"),
            "monthly_avg_percent": avg("monthly"),
            "allocated_usd": {
                window: QUOTA_LIMITS_USD[window] * total_accounts for window in _WINDOWS
            },
            "estimated_used_usd": {
                window: estimated_used(window) for window in _WINDOWS
            },
        }
