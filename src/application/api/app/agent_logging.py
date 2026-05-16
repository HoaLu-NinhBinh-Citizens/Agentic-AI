import logging


LOGGING_LEVEL = logging.INFO
LOGGING_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"


def configure_logging() -> None:
    logging.basicConfig(level=LOGGING_LEVEL, format=LOGGING_FORMAT)


configure_logging()
