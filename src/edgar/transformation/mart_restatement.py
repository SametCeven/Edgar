import numpy as np
import pandas as pd
from edgar.config import Config
from edgar.shared import AppLogger, read_csv, write_csv

# mart_restatement (Task 2, classification) — one row per original filing (10-K/10-Q).
# Reads int_filing (filing grain; carries was_restated = an amendment exists for the same
# (cik, report_date)) joined to a financial snapshot from int_financial at (cik, report_date).
# Alternative target int_financial.was_restated (a value changed in a later filing) measures
# something different.
CONFIG_MODEL = {
    "output_csv": "mart_restatement.csv",
    "output_cols": [
        "accession_number",
        "cik",
        "ticker",
        "name",
        "sector",
        "sic_description",
        "exchange",
        "state_of_incorporation",
        "fiscal_year_end",
        "form",
        "report_date",
        "report_year",
        "report_quarter",
        "filing_date",
        "filing_lag_days",
        "is_xbrl",
        "is_inline_xbrl",
        "total_assets",
        "net_income",
        "revenue",
        "total_equity",
        "leverage",
        "debt_to_equity",
        "current_ratio",
        "roa",
        "net_margin",
        "was_restated",
    ],
}


def _extract(config: Config, logger: AppLogger) -> dict:
    logger.info("Started extract")
    filing = read_csv(
        logger,
        config.int_dir / "int_filing.csv",
        dtype={"accession_number": "string", "cik": "string", "form": "string"},
        parse_dates=["filing_date", "report_date"],
    )
    fin = read_csv(
        logger,
        config.int_dir / "int_financial.csv",
        dtype={"cik": "string", "normalized_concept": "string"},
        parse_dates=["end_date"],
    )
    logger.info("Completed extract")
    return {"filing": filing, "fin": fin}


def _transform(config: Config, logger: AppLogger, extracted: dict) -> pd.DataFrame:
    logger.info("Started transform")
    filing = extracted["filing"]
    originals = filing[~filing["is_amendment"]].copy()

    # financial snapshot joined on (cik, report_date == end_date). Flows (revenue,
    # net_income) match by duration: annual for 10-K (FY end), quarter for 10-Q (quarter
    # end). Instant balance-sheet items match both. Without "quarter", net_income/revenue
    # are NaN for every 10-Q (~75% of rows). On the rare FY-end collision (a discretely
    # tagged Q4), prefer annual so 10-K flows stay full-year.
    fin = extracted["fin"]
    sub = fin[fin["duration_type"].isin(["annual", "quarter", "instant"])].copy()
    sub["_dur_rank"] = sub["duration_type"].map({"annual": 0, "quarter": 1, "instant": 2})
    sub = sub.sort_values("_dur_rank").drop_duplicates(
        ["cik", "end_date", "normalized_concept"], keep="first"
    )
    wide = sub.pivot_table(
        index=["cik", "end_date"],
        columns="normalized_concept",
        values="val",
        aggfunc="first",
    ).reset_index()
    for c in [
        "total_assets",
        "net_income",
        "total_liabilities",
        "total_equity",
        "revenue",
        "current_assets",
        "current_liabilities",
    ]:
        if c not in wide.columns:
            wide[c] = pd.NA
    wide["leverage"] = wide["total_liabilities"] / wide["total_assets"]
    wide["debt_to_equity"] = wide["total_liabilities"] / wide["total_equity"]
    wide["current_ratio"] = wide["current_assets"] / wide["current_liabilities"]
    wide["roa"] = wide["net_income"] / wide["total_assets"]
    wide["net_margin"] = wide["net_income"] / wide["revenue"]

    # Near-zero denominators (equity, current liabilities, revenue) blow these ratios up
    # to inf / extreme finite values that StandardScaler can't tame. Match the winsorize
    # pattern used by mart_capital_allocation / mart_revenue: inf -> NaN, then clip to [1%, 99%].
    ratio_cols = ["leverage", "debt_to_equity", "current_ratio", "roa", "net_margin"]
    wide[ratio_cols] = wide[ratio_cols].replace([np.inf, -np.inf], np.nan)
    lo, hi = wide[ratio_cols].quantile(0.01), wide[ratio_cols].quantile(0.99)
    n_clipped = int(((wide[ratio_cols] < lo) | (wide[ratio_cols] > hi)).sum().sum())
    wide[ratio_cols] = wide[ratio_cols].clip(lower=lo, upper=hi, axis=1)
    logger.info(f"mart_restatement: winsorized {n_clipped:,} ratio values to [1%, 99%]")

    df = originals.merge(
        wide[
            [
                "cik",
                "end_date",
                "total_assets",
                "net_income",
                "revenue",
                "total_equity",
                "leverage",
                "debt_to_equity",
                "current_ratio",
                "roa",
                "net_margin",
            ]
        ],
        left_on=["cik", "report_date"],
        right_on=["cik", "end_date"],
        how="left",
    )

    df = df[CONFIG_MODEL["output_cols"]]
    logger.info(
        f"mart_restatement: {len(df):,} filings; "
        f"{int(df['was_restated'].sum()):,} restated ({df['was_restated'].mean():.1%})"
    )
    logger.info("Completed transform")
    return df


def _load(config: Config, logger: AppLogger, df_transformed: pd.DataFrame) -> None:
    logger.info("Started load")
    write_csv(logger, config.mart_dir / CONFIG_MODEL["output_csv"], df_transformed)
    logger.info("Completed load")


def run(config: Config, logger: AppLogger):
    logger.info("=" * 60)
    logger.info("Started mart_restatement")
    extracted = _extract(config, logger)
    df_transformed = _transform(config, logger, extracted)
    _load(config, logger, df_transformed)
    logger.info("Completed mart_restatement")
    logger.info("=" * 60)
