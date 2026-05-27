from edgar.config import Config
from edgar.shared import AppLogger, EdgarClient

# --- Runner ---


def run(config: Config, logger: AppLogger):
    logger.info("diag_temp: JSON shape + cross-company concept/unit/form scan")
    client = EdgarClient(config, logger)
    logger.info("diag_temp: done")
