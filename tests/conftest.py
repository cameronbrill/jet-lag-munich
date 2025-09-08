import logging
import os

import pytest
from rich.console import Console
from rich.traceback import Traceback
import structlog

from core.logging import configure_logging


def _configure_pytest_loggers() -> None:
    """Configure pytest's internal loggers to use our structlog formatter."""
    # Get the structlog handler that was configured
    root_logger = logging.getLogger()
    structlog_handler = None

    # Find our structlog handler
    for handler in root_logger.handlers:
        if hasattr(handler, "formatter") and isinstance(handler.formatter, structlog.stdlib.ProcessorFormatter):
            structlog_handler = handler
            break

    if structlog_handler:
        # Apply our structlog handler to pytest's loggers
        pytest_loggers = [
            "pytest",
            "_pytest",
            "_pytest.logging",
            "_pytest.capture",
            "_pytest.main",
            "_pytest.runner",
            "_pytest.terminal",
        ]

        for logger_name in pytest_loggers:
            logger = logging.getLogger(logger_name)
            # Remove any existing handlers
            for handler in logger.handlers[:]:
                logger.removeHandler(handler)
            # Add our structlog handler
            logger.addHandler(structlog_handler)
            logger.setLevel(logging.INFO)
            logger.propagate = False  # Prevent double logging


def pytest_configure(config: pytest.Config) -> None:
    """Configure pytest with our structured logging."""
    # Configure our logging system first
    configure_logging(level="INFO", format_json=False)

    # Override pytest's default logging configuration
    # This ensures all pytest logs use our structlog formatter
    config.option.log_cli = True
    config.option.log_cli_level = "INFO"
    config.option.log_cli_format = "%(message)s"
    config.option.log_cli_date_format = "%Y-%m-%d %H:%M:%S"

    # Configure pytest's internal loggers to use our formatter
    _configure_pytest_loggers()


def pytest_sessionstart(session: pytest.Session) -> None:  # noqa: ARG001
    """Called after the Session object has been created."""
    # Ensure our logging is configured for the session
    configure_logging(level="INFO", format_json=False)
    _configure_pytest_loggers()


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    """Hook to format test reports with structlog."""
    # Only log non-failed tests here to avoid duplication with pytest_exception_interact
    if report.when == "call" and report.outcome != "failed":
        logger = structlog.get_logger("pytest")
        logger.info(
            "Test completed",
            test_name=report.nodeid,
            outcome=report.outcome,
            when=report.when,
            duration=getattr(report, "duration", None),
        )


def pytest_exception_interact(node: pytest.Item, call: pytest.CallInfo) -> None:  # pyright: ignore[reportMissingTypeArgument]
    """Hook to format exceptions with Rich when they occur."""
    if call.excinfo is not None:
        logger = structlog.get_logger("pytest")

        # Log basic exception info
        logger.error(
            "Test exception occurred",
            test_name=node.nodeid,
            exception_type=call.excinfo.typename,
            exception_message=str(call.excinfo.value),
        )

        # Render Rich traceback without re-raising the exception
        console = Console()
        traceback = Traceback.from_exception(
            call.excinfo.type,
            call.excinfo.value,
            call.excinfo.tb,
            show_locals=True,
            max_frames=5,
        )
        console.print(traceback)


def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo) -> pytest.TestReport:  # pyright: ignore[reportMissingTypeArgument]
    """Override test report generation to suppress default traceback rendering."""
    report = pytest.TestReport.from_item_and_call(item, call)

    # If the test failed, clear the longrepr to prevent pytest from showing its own traceback
    is_ci = os.getenv("GITHUB_ACTIONS") == "true"
    if report.outcome == "failed" and call.excinfo is not None and not is_ci:
        report.longrepr = None

    return report
