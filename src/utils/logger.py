import sys
from loguru import logger

from utils.context import APP_CTX


def setup_logger():

    logger.remove()

    logger.add(
        sys.stdout,
        level="INFO",
        enqueue=True,
        backtrace=True,
        diagnose=False,
    )

    logger.add(
        "logs/app.log",
        rotation="1 day",
        retention="7 days",
        enqueue=True,
    )

    APP_CTX.set_logger(logger)