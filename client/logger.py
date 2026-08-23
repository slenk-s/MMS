"""
日志模块
统一配置控制台（可选文件）日志输出，替代散落的 print("[DEBUG] ...")
日志级别由 config.LOG_LEVEL 控制（默认 INFO，DEBUG 级默认关闭）
"""
import logging
from logging.handlers import RotatingFileHandler
import os
import sys

_DEFAULT_LOG_LEVEL = "INFO"

_CONFIGURED = False


def _configure_root() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    try:
        if "config" in sys.modules and hasattr(sys.modules["config"], "LOG_LEVEL"):
            from config import LOG_LEVEL
            level = getattr(logging, str(LOG_LEVEL).upper(), logging.INFO)
        else:
            level = getattr(logging, _DEFAULT_LOG_LEVEL.upper(), logging.INFO)
    except Exception:
        level = getattr(logging, _DEFAULT_LOG_LEVEL.upper(), logging.INFO)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(level)
    # 清理可能存在的默认 handler，避免重复输出
    for h in list(root.handlers):
        root.removeHandler(h)

    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(fmt)
    root.addHandler(console)

    # 可选文件输出：设置 LOG_FILE 环境变量即启用滚动文件日志
    log_file = os.getenv("LOG_FILE")
    if log_file:
        file_handler = RotatingFileHandler(
            log_file, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """获取命名 logger，首次调用时自动配置根 logger"""
    _configure_root()
    return logging.getLogger(name)
