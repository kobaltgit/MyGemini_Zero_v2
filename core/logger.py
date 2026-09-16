"""
Structured logging module for MyGemini Zero v2.
Provides thread-safe, rotating log files and contextual user_id filtering.
"""

import logging
from logging.handlers import RotatingFileHandler
from logging import LoggerAdapter, LogRecord
from typing import MutableMapping, Any, Optional
from core.config import LOGS_DIR

# Ensure logs directory exists
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Standard log format across console and files
LOG_FORMAT = "%(asctime)s - %(name)s:%(lineno)d - %(levelname)s - [%(user_id)s] - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class UserIdContextFilter(logging.Filter):
    """
    Ensures that the 'user_id' attribute is always present in log records.
    Defaults to 'System' if no user context was provided.
    """

    def filter(self, record: LogRecord) -> bool:
        if not hasattr(record, "user_id"):
            record.user_id = "System"
        return True


class UserIdAdapter(LoggerAdapter):
    """
    Logger adapter that automatically attaches user_id to log record extras.
    """

    def process(self, msg: str, kwargs: MutableMapping[str, Any]) -> tuple[str, MutableMapping[str, Any]]:
        if "extra" not in kwargs:
            kwargs["extra"] = {}
        if "user_id" not in kwargs["extra"]:
            kwargs["extra"]["user_id"] = self.extra.get("user_id", "System")
        return msg, kwargs


_logging_initialized = False


def setup_logging() -> None:
    """Initializes root and specialized loggers with file and console handlers."""
    global _logging_initialized
    if _logging_initialized:
        return

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
    user_id_filter = UserIdContextFilter()

    # Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(user_id_filter)

    # General Bot Handler
    general_handler = RotatingFileHandler(
        filename=LOGS_DIR / "bot_general.log",
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    general_handler.setLevel(logging.INFO)
    general_handler.setFormatter(formatter)
    general_handler.addFilter(user_id_filter)

    # Gemini API Handler
    gemini_handler = RotatingFileHandler(
        filename=LOGS_DIR / "gemini_api.log",
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=3,
        encoding="utf-8",
    )
    gemini_handler.setLevel(logging.DEBUG)
    gemini_handler.setFormatter(formatter)
    gemini_handler.addFilter(user_id_filter)

    # Database Handler
    db_handler = RotatingFileHandler(
        filename=LOGS_DIR / "database.log",
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=3,
        encoding="utf-8",
    )
    db_handler.setLevel(logging.DEBUG)
    db_handler.setFormatter(formatter)
    db_handler.addFilter(user_id_filter)

    # User Messages Handler
    user_msg_handler = RotatingFileHandler(
        filename=LOGS_DIR / "user_messages.log",
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    user_msg_handler.setLevel(logging.INFO)
    user_msg_handler.setFormatter(formatter)
    user_msg_handler.addFilter(user_id_filter)

    # Root Logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)
    root_logger.addHandler(general_handler)

    # Specific Loggers
    def configure_named_logger(name: str, level: int, file_handler: RotatingFileHandler):
        log = logging.getLogger(name)
        log.setLevel(level)
        log.handlers.clear()
        log.addHandler(console_handler)
        log.addHandler(file_handler)
        log.propagate = False

    configure_named_logger("gemini_api", logging.DEBUG, gemini_handler)
    configure_named_logger("database", logging.DEBUG, db_handler)
    configure_named_logger("user_messages", logging.INFO, user_msg_handler)

    # External libraries log levels
    logging.getLogger("aiogram").setLevel(logging.INFO)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    _logging_initialized = True


def get_logger(name: str, user_id: Optional[str | int] = None) -> UserIdAdapter:
    """
    Returns a configured logger wrapped in UserIdAdapter for contextual user ID tracing.
    """
    if not _logging_initialized:
        setup_logging()
    logger = logging.getLogger(name)
    user_id_str = str(user_id) if user_id is not None else "System"
    return UserIdAdapter(logger, {"user_id": user_id_str})
