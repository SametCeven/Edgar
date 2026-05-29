import json
import pandas as pd
from edgar.config import Config
from edgar.shared import AppLogger, read_csv, write_csv

CONFIG_MODEL = {
    "output_csv": "dim_company.csv",
    "rename_map": {
        "sicDescription": "sic_description",
        "stateOfIncorporation": "state_of_incorporation",
        "fiscalYearEnd": "fiscal_year_end",
        "entityType": "entity_type",
    },
    "output_cols": [
        "cik",
        "ticker",
        "name",
        "sector",
        "sic",
        "sic_description",
        "state_of_incorporation",
        "fiscal_year_end",
        "exchange",
        "entity_type",
    ],
}


# exchanges/tickers are stored as JSON list strings (e.g. '["NYSE"]'); take first
def _first_json(raw) -> str | None:
    try:
        items = json.loads(raw) if isinstance(raw, str) else []
        return items[0] if items else None
    except (json.JSONDecodeError, TypeError):
        return None


def _extract(config: Config, logger: AppLogger) -> dict[str, pd.DataFrame]:
    logger.info("Started extract")
    companies = read_csv(
        logger,
        config.raw_dir / "raw_companies.csv",
        dtype={"cik": "string", "sic": "string", "fiscalYearEnd": "string"},
    )
    iwb = read_csv(logger, config.company_1000_csv_path, dtype={"cik": "string"})
    logger.info("Completed extract")
    return {"raw_companies": companies, "company_1000": iwb}


def _transform(
    config: Config, logger: AppLogger, extracted: dict[str, pd.DataFrame]
) -> pd.DataFrame:
    logger.info("Started transform")
    companies = extracted["raw_companies"]
    iwb = extracted["company_1000"][["cik", "ticker", "sector"]]

    # merge to get sector data from iwb
    df = companies.merge(iwb, on="cik", how="left")
    df["exchange"] = df["exchanges"].apply(_first_json)
    df = df.rename(columns=CONFIG_MODEL["rename_map"])
    df = df[CONFIG_MODEL["output_cols"]]

    missing_sector = int(df["sector"].isna().sum())
    if missing_sector:
        logger.warning(
            f"dim_company: {missing_sector} rows missing sector (no IWB match)"
        )
    logger.info(f"dim_company: {len(df):,} rows")
    logger.info("Completed transform")
    return df


def _load(config: Config, logger: AppLogger, df_transformed: pd.DataFrame) -> None:
    logger.info("Started load")
    write_csv(logger, config.dim_dir / CONFIG_MODEL["output_csv"], df_transformed)
    logger.info("Completed load")


def run(config: Config, logger: AppLogger):
    logger.info("=" * 60)
    logger.info("Started dim_company")
    extracted = _extract(config, logger)
    df_transformed = _transform(config, logger, extracted)
    _load(config, logger, df_transformed)
    logger.info("Completed dim_company")
    logger.info("=" * 60)
