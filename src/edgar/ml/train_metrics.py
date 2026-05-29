import pandas as pd
from edgar.config import Config
from edgar.shared import AppLogger, write_csv

# ml_metrics — tidy table, one row per (task, metric), collected from the four
# train modules' run() returns. Persisted so Power BI metric cards are
# data-driven: ROC-AUC (Task 2) and silhouette / davies_bouldin / inertia
# (Tasks 3-4) otherwise exist only in the training log.
CONFIG_MODEL = {
    "output_csv": "ml_metrics.csv",
    "output_cols": ["task", "metric", "value"],
}


def run(config: Config, logger: AppLogger, rows: list[dict]) -> None:
    logger.info("=" * 60)
    logger.info("Started train_metrics")
    df = pd.DataFrame(rows, columns=CONFIG_MODEL["output_cols"])
    write_csv(logger, config.ml_dir / CONFIG_MODEL["output_csv"], df)
    logger.info(
        f"train_metrics: {len(df):,} metrics across {df['task'].nunique()} tasks"
    )
    logger.info("Completed train_metrics")
    logger.info("=" * 60)
