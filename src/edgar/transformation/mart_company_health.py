import numpy as np
import pandas as pd
from edgar.config import Config
from edgar.shared import AppLogger, read_csv, write_csv

# mart_company_health (Task 4, clustering) — one row per company, latest period.
# Distress ratios: leverage, liquidity, profitability, coverage.
CONFIG_MODEL = {
    "output_csv": "mart_company_health.csv",
    "output_cols": [
        "cik",
        "ticker",
        "name",
        "sector",
        "sic_description",
        "exchange",
        "state_of_incorporation",
        "fiscal_year_end",
        "end_date",
        "end_year",
        "end_quarter",
        "total_assets",
        "total_liabilities",
        "total_equity",
        "revenue",
        "net_income",
        "working_capital",
        "debt_to_assets",
        "debt_to_equity",
        "current_ratio",
        "roa",
        "net_margin",
        "equity_ratio",
        "interest_coverage",
        "cfo_to_debt",
    ],
}


COMPANY_COLS = [
    "cik",
    "ticker",
    "name",
    "sector",
    "sic_description",
    "exchange",
    "state_of_incorporation",
    "fiscal_year_end",
]


def _extract(config: Config, logger: AppLogger) -> dict:
    logger.info("Started extract")
    fin = read_csv(
        logger,
        config.int_dir / "int_financial.csv",
        dtype={
            "cik": "string",
            "normalized_concept": "string",
            "ticker": "string",
            "name": "string",
            "sector": "string",
        },
        parse_dates=["end_date"],
    )
    logger.info("Completed extract")
    return {"fin": fin}


def _transform(config: Config, logger: AppLogger, extracted: dict) -> pd.DataFrame:
    logger.info("Started transform")
    fin = extracted["fin"]
    sub = fin[fin["duration_type"].isin(["annual", "instant"])]
    wide = sub.pivot_table(
        index=["cik", "end_date"],
        columns="normalized_concept",
        values="val",
        aggfunc="first",
    ).reset_index()
    wide = wide.sort_values(["cik", "end_date"]).drop_duplicates("cik", keep="last")

    def col(name):
        return (
            wide[name] if name in wide.columns else pd.Series(pd.NA, index=wide.index)
        )

    total_debt = col("long_term_debt").fillna(0) + col("current_debt").fillna(0)
    wide["debt_to_assets"] = total_debt / col("total_assets")
    wide["debt_to_equity"] = total_debt / col("total_equity")
    wide["current_ratio"] = col("current_assets") / col("current_liabilities")
    wide["roa"] = col("net_income") / col("total_assets")
    wide["interest_coverage"] = col("operating_income") / col("interest_expense")
    wide["cfo_to_debt"] = col("cf_operating") / total_debt.replace(0, pd.NA)

    # Near-zero denominators (equity, current liabilities, interest expense, debt) blow these
    # ratios up to extreme finite values StandardScaler can't tame, collapsing KMeans into one
    # blob + outlier singletons (false-high silhouette). Match mart_capital_allocation /
    # mart_restatement: inf -> NaN, then clip to [1%, 99%]. Clustering features only — net_margin
    # / equity_ratio are PBI context (excluded from the model) and stay unclipped.
    feature_ratios = [
        "debt_to_assets", "debt_to_equity", "current_ratio", "roa",
        "interest_coverage", "cfo_to_debt",
    ]
    ratios = wide[feature_ratios].apply(pd.to_numeric, errors="coerce").replace(
        [np.inf, -np.inf], np.nan
    )
    lo, hi = ratios.quantile(0.01), ratios.quantile(0.99)
    n_clipped = int(((ratios < lo) | (ratios > hi)).sum().sum())
    wide[feature_ratios] = ratios.clip(lower=lo, upper=hi, axis=1)
    logger.info(f"mart_company_health: winsorized {n_clipped:,} ratio values to [1%, 99%]")

    wide["net_margin"] = col("net_income") / col("revenue")
    wide["equity_ratio"] = col("total_equity") / col("total_assets")
    wide["working_capital"] = col("current_assets") - col("current_liabilities")
    # absolute $ context for PBI (carried so dashboards need no join back to int/dim)
    wide["total_assets"] = col("total_assets")
    wide["total_liabilities"] = col("total_liabilities")
    wide["total_equity"] = col("total_equity")
    wide["revenue"] = col("revenue")
    wide["net_income"] = col("net_income")
    wide["end_year"] = wide["end_date"].dt.year
    wide["end_quarter"] = wide["end_date"].dt.quarter

    comp = extracted["fin"][COMPANY_COLS].drop_duplicates("cik")
    df = wide.merge(comp, on="cik", how="left")
    df = df[CONFIG_MODEL["output_cols"]]
    logger.info(f"mart_company_health: {len(df):,} companies")
    logger.info("Completed transform")
    return df


def _load(config: Config, logger: AppLogger, df_transformed: pd.DataFrame) -> None:
    logger.info("Started load")
    write_csv(logger, config.mart_dir / CONFIG_MODEL["output_csv"], df_transformed)
    logger.info("Completed load")


def run(config: Config, logger: AppLogger):
    logger.info("=" * 60)
    logger.info("Started mart_company_health")
    extracted = _extract(config, logger)
    df_transformed = _transform(config, logger, extracted)
    _load(config, logger, df_transformed)
    logger.info("Completed mart_company_health")
    logger.info("=" * 60)
