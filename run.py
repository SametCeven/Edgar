import argparse
from edgar.config import Config
from edgar.shared import AppLogger
from edgar.orchestration import pipeline
from scripts import diag_temp

STEPS = ["preprocess", "fetch", "parse", "load", "transform", "train"]


def parse_args():
    parser = argparse.ArgumentParser(description="Edgar Pipeline Runner")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser(
        "pipeline", help="Run pipeline (all steps, or selected via flags)"
    )
    for step in STEPS:
        p.add_argument(f"--{step}", action="store_true", help=f"Run {step} step")

    sub.add_parser("diag-temp", help="Run scripts/diag_temp.py")

    return parser.parse_args()


def main():
    config = Config()
    logger = AppLogger(level_str=config.log_level, log_dir=config.log_dir)

    args = parse_args()
    logger.info(f"Starting App (Command:{args.command})")

    if args.command == "pipeline":
        selected = [s for s in STEPS if getattr(args, s)]
        if not selected:
            selected = STEPS
        ordered = [s for s in STEPS if s in selected]
        pipeline.run(config, logger, steps=ordered)
    elif args.command == "diag-temp":
        diag_temp.run(config, logger)


if __name__ == "__main__":
    main()
