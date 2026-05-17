import argparse
from config import Config
from src import AppLogger


def parse_args():
    parser = argparse.ArgumentParser(description="ML Pipeline Runner")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("ingest", help="Fetch data from SEC → BigQuery")
    subparsers.add_parser("transform", help="Run DBT transformations")
    subparsers.add_parser("train", help="Train ML model (BigQuery IO)")
    subparsers.add_parser("pipeline", help="Run full pipeline")
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


if __name__ == "__main__":
    main()
