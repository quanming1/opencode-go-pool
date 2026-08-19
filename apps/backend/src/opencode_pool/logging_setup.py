"""统一日志配置。"""

import logging

_FORMAT = "%(asctime)s - %(levelname)-7s - %(name)s - %(message)s"


def setup_logging(level: str = "INFO") -> None:
    """按级别初始化根日志（可重复调用，幂等）。"""
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO), format=_FORMAT)
