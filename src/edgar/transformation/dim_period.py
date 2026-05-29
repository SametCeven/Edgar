import numpy as np
import pandas as pd
from collections import defaultdict
from edgar.config import Config
from edgar.shared import AppLogger, read_csv_incrementally, write_csv

# dim_period catalogs every distinct (start, end) window in raw_company_facts.
# is_included marks the analytical window (end in [min_year .. today+1y], not garbage).
# duration_type: instant balances (null start) vs quarter/semi/ytd9/annual flows.
CONFIG_MODEL = {
    "output_csv": "dim_period.csv",
    "raw_source": "raw_company_facts.csv",
    "min_year": 2015,
    "output_cols": [
        "period_id",
        "start_date",
        "end_date",
        "days",
        "duration_type",
        "end_year",
        "end_quarter",
        "is_included",
        "n_rows",
    ],
}


def _extract(config: Config, logger: AppLogger) -> pd.DataFrame:
    logger.info("Started extract")
    row_counts: defaultdict = defaultdict(int)
    for chunk in read_csv_incrementally(
        logger,
        config.raw_dir / CONFIG_MODEL["raw_source"],
        usecols=["start", "end"],
        dtype={"start": "string", "end": "string"},
    ):
        chunk["start"] = pd.to_datetime(chunk["start"], errors="coerce")
        chunk["end"] = pd.to_datetime(chunk["end"], errors="coerce")
        for key, n in chunk.groupby(["start", "end"], dropna=False).size().items():
            row_counts[key] += int(n)
    df = pd.DataFrame(
        [(s, e, n) for (s, e), n in row_counts.items()],
        columns=["start_date", "end_date", "n_rows"],
    )
    logger.info(f"dim_period: {len(df):,} distinct (start, end) in raw facts")
    logger.info("Completed extract")
    return df


def _transform(
    config: Config, logger: AppLogger, extracted: pd.DataFrame
) -> pd.DataFrame:
    logger.info("Started transform")
    df = extracted
    # day-resolution diff — ns timedelta overflows int64 when garbage rows pair an
    # early start with a far-future end (span > ~292 years). [D] cannot overflow.
    end_d = df["end_date"].to_numpy("datetime64[D]").astype("float64")
    start_d = df["start_date"].to_numpy("datetime64[D]").astype("float64")
    df["days"] = end_d - start_d
    df["end_year"] = df["end_date"].dt.year.astype("Int64")
    df["end_quarter"] = df["end_date"].dt.quarter.astype("Int64")

    conds = [
        df["start_date"].isna(),
        df["days"].between(0, 100),
        df["days"].between(101, 195),
        df["days"].between(196, 285),
        df["days"].between(286, 380),
    ]
    df["duration_type"] = np.select(
        conds, ["instant", "quarter", "semi", "ytd9", "annual"], default="other"
    )

    max_date = pd.Timestamp.now().normalize() + pd.DateOffset(years=1)
    df["is_included"] = (
        df["end_date"].notna()
        & (df["end_year"] >= CONFIG_MODEL["min_year"])
        & (df["end_date"] <= max_date)
    )
    # NaT dates cast to a huge int64-min sentinel (not NaN), so the float diff for
    # null-endpoint rows (e.g. instant balances) is finite but overflows int64.
    # Derive the null mask from the date columns and cast only valid-span rows.
    _valid = (df["start_date"].notna() & df["end_date"].notna()).to_numpy()
    _d = df["days"].to_numpy()
    _int = np.zeros(len(_d), dtype="int64")
    _int[_valid] = _d[_valid].astype("int64")
    df["days"] = pd.arrays.IntegerArray(_int, ~_valid)

    df = df.sort_values(
        ["is_included", "end_date", "start_date"], ascending=[False, True, True]
    ).reset_index(drop=True)
    df.insert(0, "period_id", range(1, len(df) + 1))
    df = df[CONFIG_MODEL["output_cols"]]

    logger.info(
        f"dim_period: {len(df):,} periods; {int(df['is_included'].sum())} included"
    )
    logger.info("Completed transform")
    return df


def _load(config: Config, logger: AppLogger, df_transformed: pd.DataFrame) -> None:
    logger.info("Started load")
    write_csv(logger, config.dim_dir / CONFIG_MODEL["output_csv"], df_transformed)
    logger.info("Completed load")


def run(config: Config, logger: AppLogger):
    logger.info("=" * 60)
    logger.info("Started dim_period")
    extracted = _extract(config, logger)
    df_transformed = _transform(config, logger, extracted)
    _load(config, logger, df_transformed)
    logger.info("Completed dim_period")
    logger.info("=" * 60)
