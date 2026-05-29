import pandas as pd
from edgar.config import Config
from edgar.shared import AppLogger, read_csv, write_csv

# dim_form catalogs every distinct filing form in raw_filings, then flags the
# analytical subset via CONFIG_MODEL["form_mapping"]. int_* filter on is_included.
# fmt: off
CONFIG_MODEL = {
    "output_csv": "dim_form.csv",
    "raw_source": "raw_filings.csv",
    "output_cols": [
        "form_id", "form", "is_annual", "is_quarterly", "is_amendment",
        "is_included", "n_filings", "n_companies",
    ],
    # (form, is_annual, is_quarterly, is_amendment)
    "form_mapping": [
        ("10-K",   True,  False, False),
        ("10-Q",   False, True,  False),
        ("10-K/A", True,  False, True),
        ("10-Q/A", False, True,  True),
    ],
}
# fmt: on


def _extract(config: Config, logger: AppLogger) -> pd.DataFrame:
    logger.info("Started extract")
    df = read_csv(
        logger,
        config.raw_dir / CONFIG_MODEL["raw_source"],
        usecols=["cik", "form"],
        dtype={"cik": "string", "form": "string"},
    )
    logger.info("Completed extract")
    return df


def _transform(
    config: Config, logger: AppLogger, extracted: pd.DataFrame
) -> pd.DataFrame:
    logger.info("Started transform")
    agg = (
        extracted.groupby("form")
        .agg(n_filings=("cik", "size"), n_companies=("cik", "nunique"))
        .reset_index()
    )
    wl = pd.DataFrame(
        CONFIG_MODEL["form_mapping"],
        columns=["form", "is_annual", "is_quarterly", "is_amendment"],
    )

    missing = set(wl["form"]) - set(agg["form"])
    if missing:
        logger.warning(f"dim_form: mapped forms absent from filings: {sorted(missing)}")

    df = agg.merge(wl, on="form", how="left")
    df["is_included"] = df["is_annual"].notna()
    for c in ["is_annual", "is_quarterly", "is_amendment"]:
        df[c] = df[c].astype("boolean").fillna(False).astype(bool)

    df = df.sort_values(
        ["is_included", "n_filings"], ascending=[False, False]
    ).reset_index(drop=True)
    df.insert(0, "form_id", range(1, len(df) + 1))
    df = df[CONFIG_MODEL["output_cols"]]

    logger.info(f"dim_form: {len(df):,} forms; {int(df['is_included'].sum())} included")
    logger.info("Completed transform")
    return df


def _load(config: Config, logger: AppLogger, df_transformed: pd.DataFrame) -> None:
    logger.info("Started load")
    write_csv(logger, config.dim_dir / CONFIG_MODEL["output_csv"], df_transformed)
    logger.info("Completed load")


def run(config: Config, logger: AppLogger):
    logger.info("=" * 60)
    logger.info("Started dim_form")
    extracted = _extract(config, logger)
    df_transformed = _transform(config, logger, extracted)
    _load(config, logger, df_transformed)
    logger.info("Completed dim_form")
    logger.info("=" * 60)
