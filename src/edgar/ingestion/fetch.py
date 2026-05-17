from edgar.config import Config
from edgar.shared import AppLogger


def run(config: Config, logger: AppLogger):
    logger.info("fetch")
