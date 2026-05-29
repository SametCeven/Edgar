from edgar.config import Config
from edgar.shared import AppLogger
from edgar.ml import (
    train_revenue,
    train_restatement,
    train_capital_allocation,
    train_company_health,
    train_metrics,
)


def run(config: Config, logger: AppLogger):
    logger.info("=" * 120)
    logger.info("Started train")
    metrics = []
    metrics += train_revenue.run(config, logger)
    metrics += train_restatement.run(config, logger)
    metrics += train_capital_allocation.run(config, logger)
    metrics += train_company_health.run(config, logger)
    train_metrics.run(config, logger, metrics)
    logger.info("Completed train")
    logger.info("=" * 120)
