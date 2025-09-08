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
    # Clear any existing handlers to avoid duplicates
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Configure structlog processors
    shared_processors = [
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

    # Choose the final processor based on format preference
    if format_json:
        # JSON output for production
        final_processor = structlog.processors.JSONRenderer()
        shared_processors.append(structlog.processors.dict_tracebacks)  # pyright: ignore[reportArgumentType]
    else:
        # Console output for development - use Rich console renderer without Rich tracebacks
        # Rich tracebacks will be handled by pytest hooks to avoid duplication
        final_processor = structlog.dev.ConsoleRenderer(
            colors=True,
            # Don't use RichTracebackFormatter here to avoid duplication
        )

    # Configure structlog
    structlog.configure(
        processors=[*shared_processors, final_processor],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure standard library logging to use structlog formatting
    # Use a simpler processor chain for standard library logging to avoid duplication
    stdlib_processors = [
        structlog.stdlib.add_log_level,
        # Don't add timestamp here - let the renderer handle it
        structlog.processors.CallsiteParameterAdder(
            parameters=[
                structlog.processors.CallsiteParameter.FILENAME,
                structlog.processors.CallsiteParameter.FUNC_NAME,
                structlog.processors.CallsiteParameter.LINENO,
            ]
        ),
    ]

    # Configure standard library logging to use structlog formatting
    formatter = structlog.stdlib.ProcessorFormatter(
        processor=final_processor,
        foreign_pre_chain=stdlib_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    # Set up root logger
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, level.upper()))


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
