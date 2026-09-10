"""ログ設定。失敗工程を特定できるよう、工程名（stage）をログに含める。"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .config import get_config

_configured = False


def setup_logging() -> logging.Logger:
    global _configured
    logger = logging.getLogger("pptx_web_bridge")
    if _configured:
        return logger
    cfg = get_config()
    level_name = str(cfg.get("logging.level", "INFO")).upper()
    logger.setLevel(getattr(logging, level_name, logging.INFO))
    fmt = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    try:
        # Windows の cp932 コンソールでも例外にしない
        if hasattr(console.stream, "reconfigure"):
            console.stream.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
    logger.addHandler(console)

    try:
        logs_dir = cfg.path("logs_dir")
        logs_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            logs_dir / str(cfg.get("logging.file_name", "app.log")),
            maxBytes=int(cfg.get("logging.max_bytes", 2000000)),
            backupCount=int(cfg.get("logging.backup_count", 3)),
            encoding="utf-8",
        )
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
    except OSError:
        # ログディレクトリが作れなくてもアプリは起動させる（コンソール出力のみ）
        logger.warning("ログファイルを作成できません。コンソール出力のみで継続します。")
    _configured = True
    return logger


def get_logger(stage: str | None = None) -> logging.Logger:
    base = setup_logging()
    return base.getChild(stage) if stage else base
