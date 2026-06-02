import pandas as pd
from edgar.config import Config
from edgar.shared import AppLogger, EdgarClient, read_csv


def run(config: Config, logger: AppLogger):
    logger.info("Started diag_temp")
    edgar_client = EdgarClient(config, logger)
    logger.info("Completed diag_temp")
