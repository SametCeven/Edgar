from edgar.config import Config
from edgar.shared import AppLogger, EdgarClient
from edgar.ingestion import preprocess, fetch, load
from edgar.transformation import transform
from edgar.ml import train


def run(config: Config, logger: AppLogger, steps: list[str]):
    logger.info(f"Pipeline starting: steps={steps}")

    client = EdgarClient(config, logger)

    if "preprocess" in steps:
        preprocess.run(config, logger, client)
    if "fetch" in steps:
        fetch.run(config, logger, client)
    if "load" in steps:
        load.run(config, logger)
    if "transform" in steps:
        transform.run(config, logger)
    if "train" in steps:
        train.run(config, logger)

    logger.info("Pipeline complete")
