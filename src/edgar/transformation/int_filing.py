import pandas as pd
from edgar.config import Config
from edgar.shared import AppLogger, read_csv, write_csv

# int_filing — canonical filing table, denormalized so marts read it alone. One row per
# accession_number for the included forms within the analytical window, carrying dim_form
# flags + company attributes. was_restated = an amendment (is_amendment form) exists for the
# same (cik, report_date); only originals are flagged.
CONFIG_MODEL = {
    "output_csv": "int_filing.csv",
    "raw_source": "raw_filings.csv",
    "min_year": 2015,
    "rename_map": {
        "accessionNumber": "accession_number",
        "filingDate": "filing_date",
        "reportDate": "report_date",
        "acceptanceDateTime": "acceptance_datetime",
        "primaryDocument": "primary_document",
        "primaryDocDescription": "primary_doc_description",
        "isXBRL": "is_xbrl",
        "isInlineXBRL": "is_inline_xbrl",
    },
    "company_cols": [
        "cik",
        "ticker",
        "name",
        "sector",
        "sic_description",
        "exchange",
        "state_of_incorporation",
        "fiscal_year_end",
    ],
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
        "is_annual",
        "is_quarterly",
        "is_amendment",
        "report_date",
        "report_year",
        "report_quarter",
        "filing_date",
        "filing_lag_days",
        "acceptance_datetime",
        "is_xbrl",
        "is_inline_xbrl",
        "was_restated",
    ],
}


def _extract(config: Config, logger: AppLogger) -> dict:
    logger.info("Started extract")
    filings = read_csv(
        logger,
        config.raw_dir / CONFIG_MODEL["raw_source"],
        dtype={"cik": "string", "accessionNumber": "string", "form": "string"},
    )
    form = read_csv(logger, config.dim_dir / "dim_form.csv", dtype={"form": "string"})
    company = read_csv(
        logger,
        config.dim_dir / "dim_company.csv",
        dtype={
            "cik": "string",
            "ticker": "string",
            "name": "string",
            "sector": "string",
        },
    )
    logger.info("Completed extract")
    return {"filings": filings, "form": form, "company": company}


def _transform(config: Config, logger: AppLogger, extracted: dict) -> pd.DataFrame:
    logger.info("Started transform")
    df = extracted["filings"].rename(columns=CONFIG_MODEL["rename_map"])
    df["filing_date"] = pd.to_datetime(df["filing_date"], errors="coerce")
    df["report_date"] = pd.to_datetime(df["report_date"], errors="coerce")

    form = extracted["form"]
    form_set = set(form.loc[form["is_included"], "form"])

    n0 = len(df)
    df = df[
        df["form"].isin(form_set)
        & (df["filing_date"].dt.year >= CONFIG_MODEL["min_year"])
    ]
    logger.info(f"int_filing: {n0:,} → {len(df):,} after form+time filter")

    dupes = int(df["accession_number"].duplicated().sum())
    if dupes:
        logger.warning(f"int_filing: {dupes:,} duplicate accession_number rows dropped")
        df = df.drop_duplicates(subset="accession_number", keep="first")

    # dim_form flags by join (single source of truth, not re-derived inline)
    df = df.merge(
        form[["form", "is_annual", "is_quarterly", "is_amendment"]], on="form", how="left"
    )

    # was_restated — an amendment exists for the same (cik, report_date); originals only.
    # Exclude NaT report_date: tuple equality checks identity first and pd.NaT is a singleton,
    # so (cik, NaT) would spuriously match another (cik, NaT) even though NaT != NaT.
    amend = df[df["is_amendment"] & df["report_date"].notna()]
    amend_keys = set(zip(amend["cik"], amend["report_date"]))
    df["was_restated"] = [
        (not a) and pd.notna(d) and ((c, d) in amend_keys)
        for a, c, d in zip(df["is_amendment"], df["cik"], df["report_date"])
    ]
    df["filing_lag_days"] = (df["filing_date"] - df["report_date"]).dt.days
    df["report_year"] = df["report_date"].dt.year
    df["report_quarter"] = df["report_date"].dt.quarter

    df = df.merge(extracted["company"][CONFIG_MODEL["company_cols"]], on="cik", how="left")

    df = df[CONFIG_MODEL["output_cols"]]
    logger.info(
        f"int_filing: {len(df):,} filings; {int(df['was_restated'].sum()):,} with amendment "
        f"({df['was_restated'].mean():.1%})"
    )
    logger.info("Completed transform")
    return df


def _load(config: Config, logger: AppLogger, df_transformed: pd.DataFrame) -> None:
    logger.info("Started load")
    write_csv(logger, config.int_dir / CONFIG_MODEL["output_csv"], df_transformed)
    logger.info("Completed load")


def run(config: Config, logger: AppLogger):
    logger.info("=" * 60)
    logger.info("Started int_filing")
    extracted = _extract(config, logger)
    df_transformed = _transform(config, logger, extracted)
    _load(config, logger, df_transformed)
    logger.info("Completed int_filing")
    logger.info("=" * 60)