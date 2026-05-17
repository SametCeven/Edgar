from edgar.config import Config
from edgar.shared import AppLogger, EdgarClient
from edgar.ingestion import preprocess, fetch, parse, load
from edgar.transformation import transform
from edgar.ml import train


def run(config: Config, logger: AppLogger, steps: list[str]):
    logger.info(f"Pipeline starting: steps={steps}")

    client = EdgarClient(config, logger)
    # db_manager = DatabaseManager(config, logger)  # add when implemented

    if "preprocess" in steps:
        preprocess.run(config, logger, client)
    if "fetch" in steps:
        fetch.run(config, logger, client)
    if "parse" in steps:
        parse.run(config, logger)
    if "load" in steps:
        load.run(config, logger)  # add db_manager when implemented
    if "transform" in steps:
        transform.run(config, logger)
    if "train" in steps:
        train.run(config, logger)  # add db_manager when implemented

    logger.info("Pipeline complete")
