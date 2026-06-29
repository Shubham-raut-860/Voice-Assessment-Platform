from __future__ import annotations

import logging
from collections.abc import Callable, MutableMapping

import structlog

from app.config import Environment, Settings

EventDict = MutableMapping[str, object]
Processor = Callable[[object, str, EventDict], EventDict | str | bytes]


def configure_logging(settings: Settings) -> None:
    timestamper: Processor = structlog.processors.TimeStamper(fmt="iso", utc=True)
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        timestamper,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer: Processor
    if settings.environment == Environment.PRODUCTION:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, settings.log_level),
    )

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    root_logger: logging.Logger = logging.getLogger()
    for handler in root_logger.handlers:
        handler.setFormatter(formatter)
