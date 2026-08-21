"""账号池查询与控制 API。"""

from fastapi import APIRouter, Depends, Request

from opencode_pool.api.auth import require_gateway_key

router = APIRouter(prefix="/api", tags=["accounts"])


@router.get("/accounts")
async def list_accounts(request: Request) -> dict:
    """返回账号池脱敏视图（不含 api_key）。"""
    pool = request.app.state.account_pool
    return {"accounts": pool.public_views()}


@router.post("/accounts/{account_id}/clear", dependencies=[Depends(require_gateway_key)])
async def clear_account(account_id: str, request: Request) -> dict:
    """清除冷却/错误计数 → healthy（PRD-C3 FR5）。"""
    pool = request.app.state.account_pool
    ok = pool.clear_account(account_id)
    if not ok:
        return {"ok": False, "error": "账号不存在"}
    account = pool.account(account_id)
    return {"ok": True, "status": account.status.value if account else "unknown"}


@router.post(
    "/accounts/{account_id}/disable", dependencies=[Depends(require_gateway_key)]
)
async def disable_account(account_id: str, request: Request) -> dict:
    """禁用账号（不参与选号）。"""
    pool = request.app.state.account_pool
    ok = pool.disable(account_id, "manual (api)")
    if not ok:
        return {"ok": False, "error": "账号不存在"}
    account = pool.account(account_id)
    return {"ok": True, "status": account.status.value if account else "unknown"}


@router.post(
    "/accounts/{account_id}/enable", dependencies=[Depends(require_gateway_key)]
)
async def enable_account(account_id: str, request: Request) -> dict:
    """启用账号。"""
    pool = request.app.state.account_pool
    ok = pool.enable(account_id)
    if not ok:
        return {"ok": False, "error": "账号不存在"}
    account = pool.account(account_id)
    return {"ok": True, "status": account.status.value if account else "unknown"}
