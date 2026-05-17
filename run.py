import argparse
import importlib
from edgar.config import Config
from edgar.shared import AppLogger

COMMANDS = {
    "fetch": {
        "fn": "edgar.ingestion.fetch.run",
        "help": "Fetch data from SEC → local cache json",
    },
    "parse": {
        "fn": "edgar.ingestion.parse.run",
        "help": "Local cache json → local csv",
    },
    "load": {
        "fn": "edgar.ingestion.load.run",
        "help": "Local csv → BigQuery",
    },
    "transform": {
        "fn": "edgar.transformation.transform.run",
        "help": "Run DBT transformations",
    },
    "train": {
        "fn": "edgar.ml.train.run",
        "help": "Train ML model (BigQuery IO)",
    },
    "pipeline": {
        "fn": "edgar.orchestration.pipeline.run",
        "help": "Run full pipeline",
    },
    "diag-temp": {
        "fn": "scripts.diag_temp.run",
        "help": "Temporary diagnostics",
    },
}


def resolve_function(path: str):
    module_path, fn_name = path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    return getattr(module, fn_name)


def parse_args():
    parser = argparse.ArgumentParser(description="ML Pipeline Runner")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name, meta in COMMANDS.items():
        subparsers.add_parser(name, help=meta["help"])

    return parser.parse_args()


def main():
    config = Config()
    logger = AppLogger(
        level_str=config.log_level,
        log_dir=config.log_dir,
    )

    args = parse_args()
    command = args.command

    logger.info(f"Starting App (Command:{command})")

    cmd = COMMANDS.get(command)
    if not cmd:
        logger.error(f"Unknown command: {command}")
        raise SystemExit(1)

    fn_path = cmd["fn"]
    logger.info(f"Resolving function: {fn_path}")

    fn = resolve_function(fn_path)

    fn(config, logger)


if __name__ == "__main__":
    main()
