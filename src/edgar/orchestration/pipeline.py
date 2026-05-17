from edgar.config import Config
from edgar.shared import AppLogger
from edgar.ingestion import preprocess, fetch, parse, load
from edgar.transformation import transform
from edgar.ml import train


def run(config: Config, logger: AppLogger):
    logger.info("Started pipeline")

    preprocess.run(config, logger)
    fetch.run(config, logger)
    parse.run(config, logger)
    load.run(config, logger)
    transform.run(config, logger)
    train.run(config, logger)

    logger.info("Completed pipeline")
