import numpy as np
import pandas as pd
from edgar.config import Config
from edgar.shared import AppLogger, read_csv, write_csv

# mart_revenue (Task 1, regression) — one row per (cik, quarter).
# Target: next-quarter revenue growth %. Uses DISCRETE quarterly revenue
# (duration_type == "quarter") only. Q4 (derivable as FY − (Q1+Q2+Q3)) is
# intentionally excluded: tested, it adds seasonal swings a linear model can't
# fit and pushed test R² negative. Revisit only with a seasonality-aware model.

# A pct change is only meaningful between genuinely adjacent fiscal periods. Gate on
# the day-distance to the comparison row so jumps across a missing quarter (the Q4
# gap) or an overlapping period become NaN instead of a spurious 2x/100x growth.
QUARTER_DAYS = (80, 100)
YEAR_DAYS = (350, 380)
CONFIG_MODEL = {
    "output_csv": "mart_revenue.csv",
    "output_cols": [
        "cik",
        "ticker",
        "name",
        "sector",
        "sic_description",
        "exchange",
        "state_of_incorporation",
        "fiscal_year_end",
        "period_id",
        "end_date",
        "end_year",
        "end_quarter",
        "fy",
        "fp",
        "revenue",
        "cogs",
        "gross_profit",
        "operating_income",
        "net_income",
        "gross_margin",
        "operating_margin",
        "net_margin",
        "revenue_qoq_growth",
        "revenue_yoy_growth",
        "target_next_q_growth",
    ],
}


def _extract(config: Config, logger: AppLogger) -> dict:
    logger.info("Started extract")
    fin = read_csv(
        logger,
        config.int_dir / "int_financial.csv",
        dtype={
            "cik": "string",
            "normalized_concept": "string",
            "fp": "string",
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
    rev = fin[
        (fin["normalized_concept"] == "revenue") & (fin["duration_type"] == "quarter")
    ].copy()
    rev = rev.sort_values(["cik", "end_date"]).drop_duplicates(
        subset=["cik", "end_date"], keep="last"
    )

    g = rev.groupby("cik")
    rev["revenue"] = rev["val"]

    gap_prev = g["end_date"].diff().dt.days
    qoq_ok = gap_prev.between(*QUARTER_DAYS)
    rev["revenue_qoq_growth"] = (rev["val"] / g["val"].shift(1) - 1).where(qoq_ok)

    gap_yoy = (rev["end_date"] - g["end_date"].shift(4)).dt.days
    yoy_ok = gap_yoy.between(*YEAR_DAYS)
    rev["revenue_yoy_growth"] = (rev["val"] / g["val"].shift(4) - 1).where(yoy_ok)

    gap_next = (g["end_date"].shift(-1) - rev["end_date"]).dt.days
    next_ok = gap_next.between(*QUARTER_DAYS)
    rev["target_next_q_growth"] = (g["val"].shift(-1) / rev["val"] - 1).where(next_ok)

    growth_cols = ["revenue_qoq_growth", "revenue_yoy_growth", "target_next_q_growth"]
    rev[growth_cols] = rev[growth_cols].replace([np.inf, -np.inf], np.nan)

    # A few micro-denominator quarters still produce extreme growth that would dominate
    # OLS squared loss. Winsorize each column to its 1st/99th percentile.
    lo, hi = rev[growth_cols].quantile(0.01), rev[growth_cols].quantile(0.99)
    n_clipped = int(((rev[growth_cols] < lo) | (rev[growth_cols] > hi)).sum().sum())
    rev[growth_cols] = rev[growth_cols].clip(lower=lo, upper=hi, axis=1)
    logger.info(
        f"mart_revenue: winsorized {n_clipped:,} growth values to [1%, 99%]"
    )

    # Other quarterly income-statement lines, for margin context (PBI / ML features).
    q = fin[fin["duration_type"] == "quarter"]
    wide = q.pivot_table(
        index=["cik", "end_date"],
        columns="normalized_concept",
        values="val",
        aggfunc="first",
    ).reset_index()
    for c in ["cogs", "gross_profit", "operating_income", "net_income"]:
        if c not in wide.columns:
            wide[c] = pd.NA
    rev = rev.merge(
        wide[["cik", "end_date", "cogs", "gross_profit", "operating_income", "net_income"]],
        on=["cik", "end_date"],
        how="left",
    )
    rev["gross_profit"] = rev["gross_profit"].fillna(rev["revenue"] - rev["cogs"])
    rev["gross_margin"] = rev["gross_profit"] / rev["revenue"]
    rev["operating_margin"] = rev["operating_income"] / rev["revenue"]
    rev["net_margin"] = rev["net_income"] / rev["revenue"]
    rev["end_year"] = rev["end_date"].dt.year
    rev["end_quarter"] = rev["end_date"].dt.quarter

    df = rev[CONFIG_MODEL["output_cols"]].dropna(subset=["target_next_q_growth"])
    logger.info(f"mart_revenue: {len(df):,} co-quarters")
    logger.info("Completed transform")
    return df


def _load(config: Config, logger: AppLogger, df_transformed: pd.DataFrame) -> None:
    logger.info("Started load")
    write_csv(logger, config.mart_dir / CONFIG_MODEL["output_csv"], df_transformed)
    logger.info("Completed load")


def run(config: Config, logger: AppLogger):
    logger.info("=" * 60)
    logger.info("Started mart_revenue")
    extracted = _extract(config, logger)
    df_transformed = _transform(config, logger, extracted)
    _load(config, logger, df_transformed)
    logger.info("Completed mart_revenue")
    logger.info("=" * 60)
