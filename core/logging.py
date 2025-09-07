"""Logging configuration for the jet-lag-munich project."""

import logging
import sys

import structlog


def configure_logging(
    level: str = "INFO",
    format_json: bool = False,
) -> None:
    """Configure structured logging for the application.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format_json: If True, output logs in JSON format, otherwise use console format
    """
    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper()),
    )

    # Configure structlog
    processors = [
        # Add log level
        structlog.stdlib.add_log_level,
        # Add timestamp
        structlog.processors.TimeStamper(fmt="iso"),
        # Add caller info
        structlog.processors.CallsiteParameterAdder(
            parameters=[
                structlog.processors.CallsiteParameter.FILENAME,
                structlog.processors.CallsiteParameter.FUNC_NAME,
                structlog.processors.CallsiteParameter.LINENO,
            ]
        ),
    ]

    if format_json:
        # JSON output for production
        processors.extend([structlog.processors.dict_tracebacks, structlog.processors.JSONRenderer()])
    else:
        # Console output for development
        processors.extend([structlog.dev.ConsoleRenderer(colors=True)])

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = __name__) -> structlog.stdlib.BoundLogger:
    """Get a configured logger instance.

    Args:
        name: Logger name, typically __name__ of the calling module

    Returns:
        Configured structlog logger
    """
    return structlog.get_logger(name)


# Configure logging on import with sensible defaults
configure_logging()
