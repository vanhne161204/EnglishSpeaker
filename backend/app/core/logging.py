"""Logging configuration."""

import logging
import sys

# Third-party libraries that log far too much at INFO (e.g. Argos Translate prints
# every token batch, which floods logs and can break non-UTF-8 consoles).
_NOISY_LOGGERS = ("argostranslate", "stanza")


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        stream=sys.stdout,
        force=True,
    )
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
