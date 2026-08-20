"""网关访问 key 管理（C3 FR1-FR3）。

设计要点：
- key 明文 `gk-` 前缀 + 随机 hex，只在创建时返回一次；库内只存 SHA-256 哈希；
- master key（.env.keys 的 GATEWAY_MASTER_KEY）不落库，与库内 key 等效；
- 鉴权是否启用 = 库内存在任一有效 key 或配置了 master key；
  两者皆无 → 兼容模式放行（本地裸跑不被破坏，PRD FR4）。
"""

import datetime as _dt
import hashlib
import secrets

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
    ) -> None:
        self._store = store
        self._master_key = master_key.strip()
        self.auth_required = auth_required

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
        return {"id": key_id, "label": label, "key": raw, "created_at": now}

    def list_keys(self) -> list[dict]:
        return self._store.list_gateway_keys()

    def revoke_key(self, key_id: int) -> bool:
        return self._store.revoke_gateway_key(key_id)

    def verify(self, raw: str) -> bool:
        """校验 bearer token：master key 或任一未吊销库内 key。"""
        token = (raw or "").strip()
        if not token:
            return False
        if self._master_key and secrets.compare_digest(token, self._master_key):
            return True
        return self._store.verify_gateway_key_hash(_hash_key(token))
