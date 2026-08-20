"""opencode_pool —— OpenCode Go 多账号合并代理后端。

职责（按 TODO 阶段演进）：
- A2：FastAPI 骨架（应用工厂 / 配置 / 日志 / 健康检查）
- B1：账号池配置与状态机（apps/backend/src/opencode_pool/accounts/）
- B2：Responses 协议透明转发
- B3：额度错误识别与自动切换
- B4：状态持久化
"""

__version__ = "0.2.0"
