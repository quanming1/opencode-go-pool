"""账号配置加载器：解析 YAML/JSON 文件，展开环境变量引用。

配置格式（config/accounts.yaml）：

    accounts:
      - id: opencode-go-1
        name: OpenCode Go 主账号
        api_key: ${OPENCODE_GO_KEY_1}   # 必填，引用环境变量
        models: []                        # 可选，空 = 全部
        enabled: true                     # 可选，默认 true

环境变量引用语法：`${VAR_NAME}`。引用缺失时跳过该账号并记录警告，
不使整个服务崩溃（FR4 安全要求：清晰错误 + 容错）。
"""

import json
import logging
import os
import re
from pathlib import Path

from opencode_pool.accounts.models import Account

logger = logging.getLogger("opencode_pool.accounts.loader")

_ENV_REF_RE = re.compile(r"^\$\{([A-Z0-9_]+)\}$")


def load_accounts(
    path: str | Path | None, env: dict[str, str] | None = None
) -> list[Account]:
    """从配置文件加载账号池。

    Args:
        path: 配置文件路径（YAML 或 JSON）。None 或不存在 → 返回空列表。
        env: 环境变量字典（默认 os.environ）。便于测试注入。

    Returns:
        已解析且密钥（env 引用）完整的账号列表。
    """
    env = env if env is not None else os.environ
    if path is None:
        return []
    p = Path(path)
    if not p.is_file():
        logger.warning("[accounts] 配置文件不存在: %s（使用空账号池）", p)
        return []

    data = _read_config(p)
    raw_accounts = data.get("accounts", [])
    accounts: list[Account] = []
    for i, raw in enumerate(raw_accounts):
        account = _parse_one(raw, i, env)
        if account is not None:
            accounts.append(account)
    return accounts


def _read_config(p: Path) -> dict:
    """按扩展名读取 YAML 或 JSON；均失败时抛清晰错误。"""
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - 依赖应在 pyproject 中声明
        raise RuntimeError("加载账号配置需要 PyYAML（pip install pyyaml）") from exc

    try:
        if p.suffix.lower() == ".json":
            return json.loads(p.read_text(encoding="utf-8"))
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ValueError(f"账号配置解析失败 {p}: {exc}") from exc


def _parse_one(
    raw: dict, index: int, env: dict[str, str]
) -> Account | None:
    """把单条配置解析为 Account；密钥缺失时警告并返回 None。

    说明：把 raw 视为 'dict' 类型契约，任何非 dict 都会走警告分支，
    避免索引访问崩溃（对齐 loader 的容错语义）。
    """
    if not isinstance(raw, dict):
        logger.warning("[accounts] 第 %d 条配置不是对象，跳过: %r", index, raw)
        return None

    account_id = raw.get("id")
    name = raw.get("name")
    raw_key = raw.get("api_key")

    if not isinstance(account_id, str) or not account_id:
        logger.warning("[accounts] 第 %d 条配置缺少 id，跳过", index)
        return None
    if not isinstance(raw_key, str) or not raw_key:
        logger.warning("[accounts] 账号 %s 缺少 api_key，跳过", account_id)
        return None

    api_key = _resolve_env(raw_key, account_id, env)
    if api_key is None:
        logger.warning(
            "[accounts] 账号 %s 的 api_key 环境变量未设置，跳过: %s",
            account_id,
            raw_key,
        )
        return None

    models = raw.get("models")
    models_tuple = (
        tuple(m for m in models if isinstance(m, str)) if isinstance(models, list) else ()
    )

    return Account(
        id=account_id,
        name=name if isinstance(name, str) and name else account_id,
        api_key=api_key,
        models=models_tuple,
        enabled=bool(raw.get("enabled", True)),
    )


def _resolve_env(raw_key: str, account_id: str, env: dict[str, str]) -> str | None:
    """解析 api_key 值；支持 ${VAR} 引用。非引用形式按字面值处理（允许本地测试）。"""
    m = _ENV_REF_RE.match(raw_key.strip())
    if not m:
        # 非环境引用：按字面密钥处理（不鼓励用于生产，便于本地/测试）
        return raw_key
    var = m.group(1)
    value = env.get(var)
    if not value:
        return None
    return value
