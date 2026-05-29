import pandas as pd
from pathlib import Path
from typing import Iterator
from .logger import AppLogger


def read_csv(logger: AppLogger, path: Path, **kwargs) -> pd.DataFrame:
    df = pd.read_csv(path, **kwargs)
    logger.info(f"read_csv: {len(df):,} rows × {len(df.columns)} cols ← {path.name}")
    return df


# chunked read for files too large to hold in memory (e.g. raw_company_facts.csv).
# yields DataFrames of chunk_size rows; caller filters/accumulates per chunk.
# pass dtype/parse_dates via kwargs to avoid mixed-type coercion on raw reads.
def read_csv_incrementally(
    logger: AppLogger, path: Path, chunk_size: int = 1_000_000, **kwargs
) -> Iterator[pd.DataFrame]:
    logger.info(f"read_csv_incrementally: ← {path.name} (chunk_size={chunk_size:,})")
    for chunk in pd.read_csv(path, chunksize=chunk_size, **kwargs):
        yield chunk


def write_csv(logger: AppLogger, path: Path, df: pd.DataFrame) -> None:
    df.to_csv(path, index=False)
    logger.info(f"write_csv: {len(df):,} rows × {len(df.columns)} cols → {path.name}")


# chunked write. caller passes first=True on the first call to truncate any
# stale file and write the header; first=False on subsequent calls to append.
def write_csv_incrementally(
    logger: AppLogger, path: Path, df: pd.DataFrame, first: bool = False
) -> None:
    if first:
        path.unlink(missing_ok=True)
    df.to_csv(
        path,
        index=False,
        mode="w" if first else "a",
        header=first,
    )
    verb = "write_csv (init)" if first else "append"
    logger.info(f"{verb}: +{len(df):,} rows → {path.name}")
