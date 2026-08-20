"""SQLite 存储层（B4）：账号运行时状态与切换历史的持久化。

设计：
- 单实例单文件；WAL 模式提升并发读。
- `save_state` 用 UPSERT 写账号一行；`write_event` 追加历史并裁剪到最近 N 条。
- DB 不可写（路径只读/目录失败）→ 构造时记 warning，所有写调用安全降级（不抛），
  保证服务在持久化不可用时仍可运行（FR7 / AC8）。
"""

import logging
import sqlite3
from pathlib import Path

from opencode_pool.accounts.models import Account

logger = logging.getLogger("opencode_pool.store.sqlite")

# 默认保留的切换历史条数
DEFAULT_HISTORY_LIMIT = 100

_SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    cooldown_until TEXT,
    last_error TEXT,
    error_count INTEGER NOT NULL DEFAULT 0,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS switch_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    account_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    reason TEXT
);
CREATE TABLE IF NOT EXISTS usage_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    account_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    error_type TEXT,
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    request_count INTEGER NOT NULL DEFAULT 1,
    model TEXT
);
CREATE TABLE IF NOT EXISTS gateway_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key_hash TEXT NOT NULL UNIQUE,
    label TEXT NOT NULL,
    created_at TEXT NOT NULL,
    revoked_at TEXT
);
"""

_UPSERT_ACCOUNT = """
INSERT INTO accounts (id, status, cooldown_until, last_error, error_count,
                      consecutive_failures, enabled)
VALUES (?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(id) DO UPDATE SET
    status = excluded.status,
    cooldown_until = excluded.cooldown_until,
    last_error = excluded.last_error,
    error_count = excluded.error_count,
    consecutive_failures = excluded.consecutive_failures,
    enabled = excluded.enabled
"""


class AccountStore:
    """SQLite 持久化仓库。所有方法在连接异常时安全降级（不抛）。"""

    def __init__(
        self,
        db_path: str,
        history_limit: int = DEFAULT_HISTORY_LIMIT,
        usage_limit: int = 2000,
    ) -> None:
        self._db_path = str(db_path)
        self._history_limit = history_limit
        self._usage_limit = usage_limit
        self._conn: sqlite3.Connection | None = None
        self._available = False
        self._connect()

    @property
    def available(self) -> bool:
        return self._available

    def _connect(self) -> None:
        try:
            path = Path(self._db_path)
            if path.parent and not path.parent.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(
                self._db_path, check_same_thread=False
            )
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(_SCHEMA)
            self._conn.commit()
            self._available = True
        except (sqlite3.Error, OSError) as exc:
            logger.warning("[store] SQLite 不可用（%s），退化为纯内存持久化", exc)
            self._conn = None
            self._available = False

    def load_accounts_state(self) -> dict[str, dict]:
        """返回 id -> 状态字段字典；不可用/空库返回 {}。"""
        if not self._available or self._conn is None:
            return {}
        try:
            cur = self._conn.execute(
                "SELECT id, status, cooldown_until, last_error, error_count, "
                "consecutive_failures, enabled FROM accounts"
            )
            rows = cur.fetchall()
            return {
                row[0]: {
                    "status": row[1],
                    "cooldown_until": row[2],
                    "last_error": row[3],
                    "error_count": row[4],
                    "consecutive_failures": row[5],
                    "enabled": bool(row[6]),
                }
                for row in rows
            }
        except sqlite3.Error as exc:
            logger.warning("[store] 读取账号状态失败: %s", exc)
            return {}

    def save_state(self, account: Account) -> None:
        """UPSERT 账号一行。实例不可用/写失败 → 记 warning 不抛。"""
        if not self._available or self._conn is None:
            return
        try:
            self._conn.execute(
                _UPSERT_ACCOUNT,
                (
                    account.id,
                    account.status.value,
                    account.cooldown_until.isoformat() if account.cooldown_until else None,
                    account.last_error,
                    account.error_count,
                    account.consecutive_failures,
                    1 if account.enabled else 0,
                ),
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            logger.warning("[store] 保存账号 %s 状态失败: %s", account.id, exc)

    def write_event(self, ts: str, account_id: str, kind: str, reason: str | None) -> None:
        """追加一条切换历史并裁剪到最近 N 条。"""
        if not self._available or self._conn is None:
            return
        try:
            self._conn.execute(
                "INSERT INTO switch_history (ts, account_id, kind, reason) VALUES (?, ?, ?, ?)",
                (ts, account_id, kind, reason),
            )
            self._conn.execute(
                "DELETE FROM switch_history WHERE id NOT IN "
                "(SELECT id FROM switch_history ORDER BY id DESC LIMIT ?)",
                (self._history_limit,),
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            logger.warning("[store] 写切换历史失败: %s", exc)

    def load_history(self, limit: int = 0) -> list[dict]:
        """返回持久化历史（新→旧），用于恢复或校验。"""
        if not self._available or self._conn is None:
            return []
        try:
            sql = "SELECT ts, account_id, kind, reason FROM switch_history ORDER BY id DESC"
            if limit and limit > 0:
                sql += " LIMIT ?"
                rows = self._conn.execute(sql, (limit,)).fetchall()
            else:
                rows = self._conn.execute(sql).fetchall()
            return [
                {"ts": r[0], "account_id": r[1], "kind": r[2], "reason": r[3]}
                for r in rows
            ]
        except sqlite3.Error as exc:
            logger.warning("[store] 读切换历史失败: %s", exc)
            return []

    # ---- C2：用量统计 ----

    def save_usage(
        self,
        ts: str,
        account_id: str,
        kind: str,
        error_type: str | None = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        model: str | None = None,
    ) -> None:
        """追加一条用量事件并裁剪到最近 N 条（默认 2000）。"""
        if not self._available or self._conn is None:
            return
        try:
            self._conn.execute(
                "INSERT INTO usage_events (ts, account_id, kind, error_type, "
                "prompt_tokens, completion_tokens, request_count, model) "
                "VALUES (?, ?, ?, ?, ?, ?, 1, ?)",
                (ts, account_id, kind, error_type, prompt_tokens, completion_tokens, model),
            )
            self._conn.execute(
                "DELETE FROM usage_events WHERE id NOT IN "
                "(SELECT id FROM usage_events ORDER BY id DESC LIMIT ?)",
                (self._usage_limit,),
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            logger.warning("[store] 写用量事件失败: %s", exc)

    def aggregate_usage(self, hours: int = 24) -> dict:
        """按小时桶聚合用量；返回 buckets / totals / per_account（PRD-C2 FR3）。"""
        empty = {
            "hours": hours,
            "totals": {
                "request_count": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "error_count": 0,
            },
            "per_account": [],
            "buckets": [],
        }
        if not self._available or self._conn is None:
            return empty
        try:
            # 小时桶（strftime 的偏移量用参数拼接，避免拼串注入）
            offset = f"-{int(hours)} hours"
            rows = self._conn.execute(
                "SELECT strftime('%Y-%m-%dT%H:00:00', ts, ?) AS bucket, "
                "SUM(request_count), SUM(prompt_tokens), SUM(completion_tokens), "
                "SUM(CASE WHEN kind='error' THEN 1 ELSE 0 END) "
                "FROM usage_events "
                "WHERE ts >= strftime('%Y-%m-%dT%H:%M:%S','now', ?) "
                "GROUP BY bucket ORDER BY bucket",
                (offset, offset),
            ).fetchall()
            buckets = [
                {
                    "ts": r[0],
                    "request_count": int(r[1] or 0),
                    "prompt_tokens": int(r[2] or 0),
                    "completion_tokens": int(r[3] or 0),
                    "error_count": int(r[4] or 0),
                }
                for r in rows
            ]
            # 汇总
            total = self._conn.execute(
                "SELECT SUM(request_count), SUM(prompt_tokens), SUM(completion_tokens), "
                "SUM(CASE WHEN kind='error' THEN 1 ELSE 0 END) FROM usage_events"
            ).fetchone()
            totals = {
                "request_count": int(total[0] or 0),
                "prompt_tokens": int(total[1] or 0),
                "completion_tokens": int(total[2] or 0),
                "error_count": int(total[3] or 0),
            }
            # 按账号
            per = self._conn.execute(
                "SELECT account_id, SUM(request_count), SUM(prompt_tokens), "
                "SUM(completion_tokens), SUM(CASE WHEN kind='error' THEN 1 ELSE 0 END) "
                "FROM usage_events GROUP BY account_id ORDER BY SUM(request_count) DESC"
            ).fetchall()
            per_account = [
                {
                    "account_id": r[0],
                    "request_count": int(r[1] or 0),
                    "prompt_tokens": int(r[2] or 0),
                    "completion_tokens": int(r[3] or 0),
                    "error_count": int(r[4] or 0),
                }
                for r in per
            ]
            return {
                "hours": hours,
                "totals": totals,
                "per_account": per_account,
                "buckets": buckets,
            }
        except sqlite3.Error as exc:
            logger.warning("[store] 聚合用量失败: %s", exc)
            return empty

    # ---- C3：网关 key 管理 ----

    def save_gateway_key(self, key_hash: str, label: str, created_at: str) -> int | None:
        """插入网关 key 哈希，返回自增 id；失败返回 None。"""
        if not self._available or self._conn is None:
            return None
        try:
            cur = self._conn.execute(
                "INSERT INTO gateway_keys (key_hash, label, created_at, revoked_at) "
                "VALUES (?, ?, ?, NULL)",
                (key_hash, label, created_at),
            )
            self._conn.commit()
            return int(cur.lastrowid) if cur.lastrowid else None
        except sqlite3.Error as exc:
            logger.warning("[store] 保存网关 key 失败: %s", exc)
            return None

    def list_gateway_keys(self) -> list[dict]:
        """网关 key 列表（不含哈希，只含元信息）。"""
        if not self._available or self._conn is None:
            return []
        try:
            rows = self._conn.execute(
                "SELECT id, label, created_at, revoked_at FROM gateway_keys "
                "ORDER BY id DESC"
            ).fetchall()
            return [
                {
                    "id": r[0],
                    "label": r[1],
                    "created_at": r[2],
                    "revoked_at": r[3],
                }
                for r in rows
            ]
        except sqlite3.Error as exc:
            logger.warning("[store] 读网关 key 列表失败: %s", exc)
            return []

    def revoke_gateway_key(self, key_id: int) -> bool:
        """吊销 key（软删，revoked_at 置当前 UTC 时间）。"""
        if not self._available or self._conn is None:
            return False
        try:
            import datetime as _dt

            now = _dt.datetime.now(_dt.UTC).isoformat()
            cur = self._conn.execute(
                "UPDATE gateway_keys SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
                (now, key_id),
            )
            self._conn.commit()
            return cur.rowcount > 0
        except sqlite3.Error as exc:
            logger.warning("[store] 吊销网关 key 失败: %s", exc)
            return False

    def verify_gateway_key_hash(self, key_hash: str) -> bool:
        """校验 key 哈希是否存在于库且未吊销。"""
        if not self._available or self._conn is None:
            return False
        try:
            row = self._conn.execute(
                "SELECT 1 FROM gateway_keys WHERE key_hash = ? AND revoked_at IS NULL",
                (key_hash,),
            ).fetchone()
            return row is not None
        except sqlite3.Error as exc:
            logger.warning("[store] 校验网关 key 失败: %s", exc)
            return False

    def has_any_gateway_key(self) -> bool:
        """是否存在网关 key 记录（含已吊销）——决定鉴权是否启用。

        注意：吊销唯一 key 不等于关闭鉴权（否则吊销 = 解锁裸奔）。
        想彻底关闭鉴权需清空 gateway_keys 表。
        """
        if not self._available or self._conn is None:
            return False
        try:
            row = self._conn.execute(
                "SELECT 1 FROM gateway_keys LIMIT 1"
            ).fetchone()
            return row is not None
        except sqlite3.Error:
            return False

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except sqlite3.Error:
                pass
            self._conn = None
