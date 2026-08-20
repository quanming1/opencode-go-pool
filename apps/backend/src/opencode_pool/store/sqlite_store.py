"""SQLite 存储层（B4 + C4）：账号运行时状态、用量事件与统一事件日志的持久化。

设计：
- 单实例单文件；WAL 模式提升并发读。
- `save_state` 用 UPSERT 写账号一行；`save_event` 追加统一事件并裁剪到最近 N 条（C4）。
- 启动时 `migrate_switch_history` 把旧 switch_history 表逐行迁入 events 后 DROP（C4）。
- DB 不可写（路径只读/目录失败）→ 构造时记 warning，所有写调用安全降级（不抛），
  保证服务在持久化不可用时仍可运行（FR7 / AC8）。
"""

import json
import logging
import sqlite3
from pathlib import Path

from opencode_pool.accounts.models import Account
from opencode_pool.events.recorder import SCHEMA_VERSION

logger = logging.getLogger("opencode_pool.store.sqlite")

# 默认保留的统一事件条数（C4：保留最近 5000 条）
DEFAULT_EVENT_LIMIT = 5000

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
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    event_time TEXT NOT NULL,
    data_json TEXT NOT NULL,
    meta_json TEXT NOT NULL
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
        usage_limit: int = 2000,
        event_limit: int = DEFAULT_EVENT_LIMIT,
    ) -> None:
        self._db_path = str(db_path)
        self._usage_limit = usage_limit
        self._event_limit = event_limit
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
            # C4：旧 switch_history 表存在则迁入 events 后删除（失败降级不影响服务）
            self.migrate_switch_history()
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

    # ---- C4：统一事件日志 ----

    def save_event(self, type_: str, event_time: str, data_json: str, meta_json: str) -> None:
        """追加一条统一事件并裁剪到最近 N 条（默认 5000）。"""
        if not self._available or self._conn is None:
            return
        try:
            self._conn.execute(
                "INSERT INTO events (type, event_time, data_json, meta_json) "
                "VALUES (?, ?, ?, ?)",
                (type_, event_time, data_json, meta_json),
            )
            self._conn.execute(
                "DELETE FROM events WHERE id NOT IN "
                "(SELECT id FROM events ORDER BY id DESC LIMIT ?)",
                (self._event_limit,),
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            logger.warning("[store] 写统一事件失败: %s", exc)

    def query_events(self, limit: int = 100, types: list[str] | None = None) -> list[dict]:
        """统一事件（新→旧），支持 type 白名单筛选与条数限制。

        单条 data/meta JSON 损坏 → 跳过该条，不影响其余。
        """
        if not self._available or self._conn is None:
            return []
        try:
            sql = "SELECT type, event_time, data_json, meta_json FROM events"
            params: list = []
            if types:
                placeholders = ",".join("?" * len(types))
                sql += f" WHERE type IN ({placeholders})"
                params.extend(types)
            sql += " ORDER BY id DESC LIMIT ?"
            params.append(max(1, min(int(limit), self._event_limit)))
            rows = self._conn.execute(sql, params).fetchall()
        except sqlite3.Error as exc:
            logger.warning("[store] 读统一事件失败: %s", exc)
            return []
        out: list[dict] = []
        for type_, event_time, data_json, meta_json in rows:
            try:
                out.append(
                    {
                        "type": type_,
                        "event_time": event_time,
                        "data": json.loads(data_json) if data_json else {},
                        "meta": json.loads(meta_json) if meta_json else {},
                    }
                )
            except json.JSONDecodeError:
                continue  # 单条坏数据降级跳过
        return out

    def migrate_switch_history(self) -> int:
        """把旧 switch_history 表逐行迁移为统一事件后 DROP（幂等，C4）。

        旧表不存在/已迁移 → 返回 0；迁移失败 → 保留旧表并降级（不影响服务）。
        """
        if not self._available or self._conn is None:
            return 0
        try:
            row = self._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='switch_history'"
            ).fetchone()
            if row is None:
                return 0
            rows = self._conn.execute(
                "SELECT ts, account_id, kind, reason FROM switch_history ORDER BY id"
            ).fetchall()
            meta_json = json.dumps(
                {"source": "migrated_switch_history", "schema_version": SCHEMA_VERSION},
                ensure_ascii=False,
            )
            for ts, account_id, kind, reason in rows:
                type_, data = _legacy_to_event(account_id, kind, reason)
                self._conn.execute(
                    "INSERT INTO events (type, event_time, data_json, meta_json) "
                    "VALUES (?, ?, ?, ?)",
                    (type_, ts, json.dumps(data, ensure_ascii=False), meta_json),
                )
            self._conn.execute("DROP TABLE switch_history")
            self._conn.commit()
            if rows:
                logger.info("[store] 迁移 %d 条 switch_history → events（已删除旧表）", len(rows))
            return len(rows)
        except sqlite3.Error as exc:
            logger.warning("[store] 迁移 switch_history 失败（保留旧表）: %s", exc)
            try:
                self._conn.rollback()
            except sqlite3.Error:
                pass
            return 0

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


def _legacy_to_event(account_id: str, kind: str, reason: str | None) -> tuple[str, dict]:
    """旧 switch_history 行 → (事件 type, data) 迁移映射（C4）。

    旧 kind 语义：recover=冷却到期恢复；auto_disable/disable/enable/clear
    为人工或自动状态操作；其余（quota/auth/server/network/error/bad_request）
    均为账号进入冷却的原因。
    """
    if kind == "recover":
        return "key_cooldown_completed", {
            "account_id": account_id,
            "previous_status": "cooldown",
            "reason": reason,
        }
    if kind == "auto_disable":
        return "key_disabled", {
            "account_id": account_id,
            "reason": reason,
            "automatic": True,
        }
    if kind == "disable":
        return "key_disabled", {
            "account_id": account_id,
            "reason": reason,
            "automatic": False,
        }
    if kind == "enable":
        return "key_enabled", {
            "account_id": account_id,
            "reason": reason,
        }
    if kind == "clear":
        return "key_cooldown_cleared", {
            "account_id": account_id,
            "previous_status": "cooldown",
            "reason": reason,
        }
    # 其余：进入冷却（旧表未存冷却参数，补默认值）
    return "key_cooldown_started", {
        "account_id": account_id,
        "reason": reason,
        "error_type": kind,
        "cooldown_until": None,
        "cooldown_seconds": 0,
        "consecutive_failures": 0,
    }
