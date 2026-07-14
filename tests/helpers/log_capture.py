"""Log-capture handler for asserting on production log output in tests.

Attach directly to the producing module's logger instead of relying on
pytest's ``caplog`` (which captures at the root logger and silently loses
records when suite-level code reconfigures root handlers or disables
propagation on an ancestor logger).

Usage:
    handler = LogCaptureHandler()
    logger = logging.getLogger("src.core.tools.creatives.listing")
    logger.addHandler(handler)
    try:
        ...exercise production...
    finally:
        logger.removeHandler(handler)
    assert any("expected message" in r for r in handler.records)
"""

import logging


class LogCaptureHandler(logging.Handler):
    """Captures formatted log records into a list for assertion in tests."""

    def __init__(self, level: int = logging.WARNING) -> None:
        super().__init__(level=level)
        self.records: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(self.format(record))
