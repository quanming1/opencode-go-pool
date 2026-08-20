"""网关访问 key 管理（C3 FR1-FR3）。

设计要点：
- key 明文 `gk-` 前缀 + 随机 hex，只在创建时返回一次；库内只存 SHA-256 哈希；
- master key（.env.keys 的 GATEWAY_MASTER_KEY）不落库，与库内 key 等效；
- 鉴权是否启用 = auth_required 显式开关（默认 False 本地免鉴权，GATEWAY_AUTH=on 才校验）；
- C4：创建/吊销产生 gateway_key_created / gateway_key_revoked 统一事件
  （data 只含 key_id/label，不含明文与哈希）。
"""

import datetime as _dt
import hashlib
import secrets

from opencode_pool.events.recorder import EventType
from opencode_pool.store.sqlite_store import AccountStore

_KEY_PREFIX = "gk-"


def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class KeyManager:
    """网关 key 生成/校验/吊销（依赖 AccountStore 同一 SQLite）。

    auth_required：本地单用户模式默认 False（全放行）；
    在 .env.keys 配 GATEWAY_AUTH=on 时为 True（完整 Bearer 校验）。
    """

    def __init__(
        self,
        store: AccountStore,
        master_key: str = "",
        auth_required: bool = False,
        event_recorder: object | None = None,
    ) -> None:
        self._store = store
        self._master_key = master_key.strip()
        self.auth_required = auth_required
        # C4：可选统一事件记录器（record(type_, data, meta) duck-typing）
        self._event_recorder = event_recorder

    @property
    def master_key(self) -> str:
        return self._master_key

    def create_key(self, label: str) -> dict | None:
        """生成新 key：明文只此一次返回；失败返回 None。"""
        raw = f"{_KEY_PREFIX}{secrets.token_hex(24)}"
        now = _dt.datetime.now(_dt.UTC).isoformat()
        key_id = self._store.save_gateway_key(_hash_key(raw), label, now)
        if key_id is None:
            return None
        self._emit(
            EventType.GATEWAY_KEY_CREATED,
            {"key_id": key_id, "label": label},
        )
        return {"id": key_id, "label": label, "key": raw, "created_at": now}

    def list_keys(self) -> list[dict]:
        return self._store.list_gateway_keys()

    def revoke_key(self, key_id: int) -> bool:
        label = next(
            (k["label"] for k in self._store.list_gateway_keys() if k["id"] == key_id),
            "",
        )
        ok = self._store.revoke_gateway_key(key_id)
        if ok:
            self._emit(
                EventType.GATEWAY_KEY_REVOKED,
                {"key_id": key_id, "label": label},
            )
        return ok

    def verify(self, raw: str) -> bool:
        """校验 bearer token：master key 或任一未吊销库内 key。"""
        token = (raw or "").strip()
        if not token:
            return False
        if self._master_key and secrets.compare_digest(token, self._master_key):
            return True
        return self._store.verify_gateway_key_hash(_hash_key(token))

    def _emit(self, type_: str, data: dict) -> None:
        """向统一事件流发射事件（C4；记录器缺失/失败一律降级）。"""
        if self._event_recorder is None:
            return
        try:
            self._event_recorder.record(type_, data, meta={"source": "gateway_keys"})
        except Exception:  # noqa: BLE001 - 事件失败不影响 key 管理
            pass
