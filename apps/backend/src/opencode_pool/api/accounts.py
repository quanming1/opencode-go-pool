"""账号池查询 API。"""

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api", tags=["accounts"])


@router.get("/accounts")
async def list_accounts(request: Request) -> dict:
    """返回账号池脱敏视图（不含 api_key）。"""
    pool = request.app.state.account_pool
    return {"accounts": pool.public_views()}
