import pandas as pd
from pathlib import Path
from .logger import AppLogger


def read_csv(logger: AppLogger, path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    logger.info(f"read_csv: {len(df):,} rows × {len(df.columns)} cols ← {path.name}")
    return df


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
