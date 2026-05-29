import pandas as pd
from edgar.config import Config
from edgar.shared import AppLogger, read_csv, write_csv

# mart_capital_allocation (Task 3, clustering) — one row per company, latest
# fiscal year. Features describe cash deployment, scaled by cf_operating.
CONFIG_MODEL = {
    "output_csv": "mart_capital_allocation.csv",
    "features": [
        "capex",
        "buybacks",
        "dividends_paid",
        "acquisitions",
        "debt_issued",
        "debt_repaid",
        "share_based_comp",
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
    annual = extracted["fin"][extracted["fin"]["duration_type"] == "annual"]
    wide = annual.pivot_table(
        index=["cik", "end_date", "fy"],
        columns="normalized_concept",
        values="val",
        aggfunc="first",
    ).reset_index()
    wide = wide.sort_values(["cik", "end_date"]).drop_duplicates("cik", keep="last")

    feats = CONFIG_MODEL["features"]
    raw_cols = feats + ["cf_operating"]
    for c in raw_cols:
        if c not in wide.columns:
            wide[c] = pd.NA
    base = wide["cf_operating"].abs().replace(0, pd.NA)
    scaled = []
    for f in feats:
        wide[f"{f}_to_cfo"] = wide[f] / base
        scaled.append(f"{f}_to_cfo")

    # Near-zero operating cash flow blows these ratios up to 60x+, which collapses
    # KMeans into one blob plus a few outlier singletons — silhouette looks great but
    # the clusters are meaningless. Winsorize each ratio to its 1st/99th percentile.
    ratios = wide[scaled].astype("float64")
    lo, hi = ratios.quantile(0.01), ratios.quantile(0.99)
    n_clipped = int(((ratios < lo) | (ratios > hi)).sum().sum())
    wide[scaled] = ratios.clip(lower=lo, upper=hi, axis=1)
    logger.info(
        f"mart_capital_allocation: winsorized {n_clipped:,} ratio values to [1%, 99%]"
    )

    # Absolute $ context for interpreting clusters in PBI (not clustering features).
    for c in ["revenue", "net_income"]:
        if c not in wide.columns:
            wide[c] = pd.NA
    wide["fcf"] = wide["cf_operating"] - wide["capex"]
    wide["total_payout"] = wide["dividends_paid"].fillna(0) + wide["buybacks"].fillna(0)
    wide["net_debt_change"] = wide["debt_issued"].fillna(0) - wide["debt_repaid"].fillna(0)
    context_cols = ["revenue", "net_income", "fcf", "total_payout", "net_debt_change"]
    wide["end_year"] = wide["end_date"].dt.year
    wide["end_quarter"] = wide["end_date"].dt.quarter

    comp = extracted["fin"][COMPANY_COLS].drop_duplicates("cik")
    wide = wide.merge(comp, on="cik", how="left")
    df = wide[
        [
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
            "fy",
        ]
        + raw_cols
        + context_cols
        + scaled
    ]
    logger.info(f"mart_capital_allocation: {len(df):,} companies")
    logger.info("Completed transform")
    return df


def _load(config: Config, logger: AppLogger, df_transformed: pd.DataFrame) -> None:
    logger.info("Started load")
    write_csv(logger, config.mart_dir / CONFIG_MODEL["output_csv"], df_transformed)
    logger.info("Completed load")


def run(config: Config, logger: AppLogger):
    logger.info("=" * 60)
    logger.info("Started mart_capital_allocation")
    extracted = _extract(config, logger)
    df_transformed = _transform(config, logger, extracted)
    _load(config, logger, df_transformed)
    logger.info("Completed mart_capital_allocation")
    logger.info("=" * 60)
