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

    def __init__(self, db_path: str, history_limit: int = DEFAULT_HISTORY_LIMIT) -> None:
        self._db_path = str(db_path)
        self._history_limit = history_limit
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
            self._conn = sqlite3.connect(self._db_path)
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

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except sqlite3.Error:
                pass
            self._conn = None
