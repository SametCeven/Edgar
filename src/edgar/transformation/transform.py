from edgar.config import Config
from edgar.shared import AppLogger
from edgar.transformation import (
    dim_company,
    dim_concept,
    dim_form,
    dim_period,
    int_filing,
    int_financial,
    mart_capital_allocation,
    mart_company_health,
    mart_restatement,
    mart_revenue,
)


def run(config: Config, logger: AppLogger):
    logger.info("=" * 120)
    logger.info("Started transform")
    # dims → int → marts (FK order)
    dim_company.run(config, logger)
    dim_concept.run(config, logger)
    dim_form.run(config, logger)
    dim_period.run(config, logger)
    int_financial.run(config, logger)
    int_filing.run(config, logger)
    mart_revenue.run(config, logger)
    mart_restatement.run(config, logger)
    mart_capital_allocation.run(config, logger)
    mart_company_health.run(config, logger)
    logger.info("Completed transform")
    logger.info("=" * 120)
