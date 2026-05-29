import pandas as pd
from edgar.config import Config
from edgar.shared import AppLogger, read_csv, read_csv_incrementally, write_csv

# int_financial — canonical financial table, denormalized so marts read it alone.
# Reads raw facts + dims directly (no fact layer). Two stages:
#   filter: keep raw rows flagged by the dims' is_included (concept/period/form) plus the
#           unit whitelist and non-empty fp.
#   canonicalize: one value per (cik, normalized_concept, period) by
#     1. concept coalescing — several raw tags map to one normalized_concept; within a
#        filing keep the most prevalent tag (highest dim_concept.n_rows).
#     2. restatement — several filings (accn) report the same (cik, concept, period); keep
#        the latest-filed value (raw `filed`); was_restated flags differing values.
CONFIG_MODEL = {
    "output_csv": "int_financial.csv",
    "raw_source": "raw_company_facts.csv",
    "unit_whitelist": {"USD", "USD/shares", "shares", "pure"},
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
        "cik",
        "ticker",
        "name",
        "sector",
        "sic_description",
        "exchange",
        "state_of_incorporation",
        "fiscal_year_end",
        "normalized_concept",
        "statement",
        "period_id",
        "end_date",
        "duration_type",
        "fp",
        "fy",
        "unit",
        "val",
        "was_restated",
        "n_versions",
    ],
}


# (start, end) → join key matching dim_period; NaT (instant) normalized to "NaT"
def _pkey(start: pd.Series, end: pd.Series) -> pd.Series:
    s = start.dt.strftime("%Y-%m-%d").fillna("NaT")
    e = end.dt.strftime("%Y-%m-%d").fillna("NaT")
    return s + "|" + e


def _extract(config: Config, logger: AppLogger) -> dict:
    logger.info("Started extract")
    concept = read_csv(
        logger,
        config.dim_dir / "dim_concept.csv",
        dtype={
            "taxonomy": "string",
            "concept": "string",
            "normalized_concept": "string",
            "statement": "string",
        },
    )
    period = read_csv(
        logger, config.dim_dir / "dim_period.csv", parse_dates=["start_date", "end_date"]
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
    chunks = read_csv_incrementally(
        logger,
        config.raw_dir / CONFIG_MODEL["raw_source"],
        usecols=[
            "cik",
            "taxonomy",
            "concept",
            "unit",
            "val",
            "start",
            "end",
            "fy",
            "fp",
            "form",
            "filed",
            "accn",
        ],
        dtype={
            "cik": "string",
            "taxonomy": "string",
            "concept": "string",
            "unit": "string",
            "fp": "string",
            "form": "string",
            "accn": "string",
            "start": "string",
            "end": "string",
            "filed": "string",
        },
    )
    logger.info("Completed extract")
    return {
        "concept": concept,
        "period": period,
        "form": form,
        "company": company,
        "chunks": chunks,
    }


def _transform(config: Config, logger: AppLogger, extracted: dict) -> pd.DataFrame:
    logger.info("Started transform")
    concept = extracted["concept"]
    period = extracted["period"]
    inc_c = concept[concept["is_included"]]
    concept_map = dict(
        zip(inc_c["taxonomy"] + "|" + inc_c["concept"], inc_c["concept_id"])
    )
    inc_p = period[period["is_included"]]
    period_map = dict(
        zip(_pkey(inc_p["start_date"], inc_p["end_date"]), inc_p["period_id"])
    )
    form_set = set(extracted["form"].loc[extracted["form"]["is_included"], "form"])
    units = CONFIG_MODEL["unit_whitelist"]
    logger.info(
        f"int_financial: {len(concept_map)} concepts, "
        f"{len(period_map):,} periods, {len(form_set)} forms in scope"
    )

    kept = []
    total = 0
    for i, chunk in enumerate(extracted["chunks"]):
        total += len(chunk)
        start = pd.to_datetime(chunk["start"], errors="coerce")
        end = pd.to_datetime(chunk["end"], errors="coerce")
        ckey = chunk["taxonomy"].astype(str) + "|" + chunk["concept"].astype(str)
        chunk["concept_id"] = ckey.map(concept_map)
        chunk["period_id"] = _pkey(start, end).map(period_map)
        mask = (
            chunk["unit"].isin(units)
            & chunk["form"].isin(form_set)
            & chunk["fp"].notna()
            & chunk["concept_id"].notna()
            & chunk["period_id"].notna()
        )
        cols = ["cik", "concept_id", "period_id", "accn", "unit", "val", "fp", "fy", "filed"]
        kept.append(chunk.loc[mask, cols])
        logger.info(
            f"  chunk {i + 1}: scanned {total:,}, kept {sum(len(k) for k in kept):,}"
        )

    df = pd.concat(kept, ignore_index=True).rename(columns={"accn": "accession_number"})
    df["concept_id"] = df["concept_id"].astype("Int64")
    df["period_id"] = df["period_id"].astype("Int64")
    df["val"] = pd.to_numeric(df["val"], errors="coerce")
    df["fy"] = pd.to_numeric(df["fy"], errors="coerce").astype("Int64")
    df["filed"] = pd.to_datetime(df["filed"], errors="coerce")
    logger.info(
        f"int_financial: {total:,} scanned → {len(df):,} kept ({len(df) / total:.1%})"
    )

    # attach concept + period attributes
    df = df.merge(
        concept[["concept_id", "normalized_concept", "statement", "n_rows"]],
        on="concept_id",
        how="inner",
    ).merge(
        period[["period_id", "end_date", "duration_type"]], on="period_id", how="inner"
    )

    # 1. concept coalescing — most prevalent tag per (cik, concept, period, accn)
    df = df.sort_values("n_rows", ascending=False).drop_duplicates(
        subset=["cik", "normalized_concept", "period_id", "accession_number"],
        keep="first",
    )

    # 2. restatement — latest filed wins; was_restated if values differ across accns
    grp = ["cik", "normalized_concept", "period_id"]
    stats = (
        df.groupby(grp)
        .agg(n_versions=("val", "size"), n_distinct_val=("val", "nunique"))
        .reset_index()
    )
    stats["was_restated"] = stats["n_distinct_val"] > 1
    df = df.sort_values("filed", ascending=False).drop_duplicates(subset=grp, keep="first")
    df = df.merge(stats[grp + ["n_versions", "was_restated"]], on=grp, how="left")

    # denormalize company attributes (so marts read int_financial alone)
    df = df.merge(extracted["company"][CONFIG_MODEL["company_cols"]], on="cik", how="left")

    df = df[CONFIG_MODEL["output_cols"]]
    logger.info(
        f"int_financial: {len(df):,} canonical rows; {int(df['was_restated'].sum()):,} restated"
    )
    logger.info("Completed transform")
    return df


def _load(config: Config, logger: AppLogger, df_transformed: pd.DataFrame) -> None:
    logger.info("Started load")
    write_csv(logger, config.int_dir / CONFIG_MODEL["output_csv"], df_transformed)
    logger.info("Completed load")


def run(config: Config, logger: AppLogger):
    logger.info("=" * 60)
    logger.info("Started int_financial")
    extracted = _extract(config, logger)
    df_transformed = _transform(config, logger, extracted)
    _load(config, logger, df_transformed)
    logger.info("Completed int_financial")
    logger.info("=" * 60)
