import pandas as pd
from edgar.config import Config
from edgar.shared import AppLogger, EdgarClient, read_csv

# Diagnostic: validate dim/fact cardinalities and surface dirt before transform.
# - dim_company:    distinct cik in raw_companies + IWB sector coverage
# - dim_form:       distinct form values in raw_filings
# - dim_concept:    distinct (taxonomy, concept) in raw_company_facts
# - dim_period:     distinct (start, end), garbage end dates, period_type breakdown
# - fact_filing:    rows after form + time filter
# - fact_financial: rows after concept + form + unit + time filter (rough)

CHUNK_SIZE = 1_000_000
FORM_WHITELIST = {"10-K", "10-Q", "10-K/A", "10-Q/A"}
UNIT_WHITELIST = {"USD", "USD/shares", "shares", "pure"}
MIN_YEAR = 2015
MAX_DATE = pd.Timestamp("2027-05-27")  # today + 1y sanity bound


def _companies(config: Config, logger: AppLogger) -> None:
    logger.info("--- dim_company ---")
    df = read_csv(logger, config.raw_dir / "raw_companies.csv")
    logger.info(f"distinct cik:               {df['cik'].nunique():,}")
    logger.info(f"null sic:                   {df['sic'].isna().sum():,}")
    logger.info(f"null state_of_incorp:       {df['stateOfIncorporation'].isna().sum():,}")
    logger.info(f"entityType breakdown:\n{df['entityType'].value_counts(dropna=False).to_string()}")
    iwb = read_csv(logger, config.company_1000_csv_path)
    iwb_ciks = set(iwb["cik"].astype(str).str.zfill(10))
    edgar_ciks = set(df["cik"].astype(str).str.zfill(10))
    logger.info(f"IWB ciks:                   {len(iwb_ciks):,}")
    logger.info(f"matched edgar ↔ IWB:        {len(edgar_ciks & iwb_ciks):,}")
    logger.info(f"edgar-only (no sector):     {len(edgar_ciks - iwb_ciks):,}")


def _filings(config: Config, logger: AppLogger) -> None:
    logger.info("--- fact_filing + dim_form ---")
    df = read_csv(logger, config.raw_dir / "raw_filings.csv")
    logger.info(f"raw rows:                   {len(df):,}")
    logger.info(f"distinct accessionNumber:   {df['accessionNumber'].nunique():,}")
    logger.info(f"form value_counts (top 15):\n{df['form'].value_counts().head(15).to_string()}")
    df["filingDate"] = pd.to_datetime(df["filingDate"], errors="coerce")
    f = df[df["form"].isin(FORM_WHITELIST) & (df["filingDate"].dt.year >= MIN_YEAR)]
    logger.info(f"after form+time filter:     {len(f):,}")
    logger.info(f"  10-K:                     {(f['form'] == '10-K').sum():,}")
    logger.info(f"  10-Q:                     {(f['form'] == '10-Q').sum():,}")
    logger.info(f"  10-K/A:                   {(f['form'] == '10-K/A').sum():,}")
    logger.info(f"  10-Q/A:                   {(f['form'] == '10-Q/A').sum():,}")
    logger.info(f"isXBRL=true (whitelisted):  {f['isXBRL'].sum():,}")


def _facts(config: Config, logger: AppLogger) -> None:
    logger.info("--- fact_financial + dim_concept + dim_period (chunked) ---")
    path = config.raw_dir / "raw_company_facts.csv"
    total = 0
    kept = 0
    concept_counts: dict[tuple, int] = {}
    period_keys: set = set()
    unit_counts: dict[str, int] = {}
    taxonomy_counts: dict[str, int] = {}
    form_counts: dict[str, int] = {}
    fp_counts: dict[str, int] = {}
    garbage_end = 0
    null_start_raw = 0

    for i, chunk in enumerate(
        pd.read_csv(
            path,
            chunksize=CHUNK_SIZE,
            dtype={"cik": "string", "taxonomy": "string", "concept": "string",
                   "unit": "string", "fp": "string", "form": "string", "accn": "string"},
            parse_dates=["start", "end", "filed"],
        )
    ):
        total += len(chunk)
        null_start_raw += chunk["start"].isna().sum()
        garbage_end += (chunk["end"] > MAX_DATE).sum()

        mask = (
            chunk["form"].isin(FORM_WHITELIST)
            & chunk["unit"].isin(UNIT_WHITELIST)
            & chunk["fp"].notna()
            & (chunk["end"].dt.year >= MIN_YEAR)
            & (chunk["end"] <= MAX_DATE)
        )
        f = chunk[mask]
        kept += len(f)

        for (tax, con), c in f.groupby(["taxonomy", "concept"]).size().items():
            concept_counts[(tax, con)] = concept_counts.get((tax, con), 0) + c
        for s, e in zip(f["start"].dt.date, f["end"].dt.date):
            period_keys.add((s, e))
        for u, c in f["unit"].value_counts().items():
            unit_counts[u] = unit_counts.get(u, 0) + c
        for t, c in f["taxonomy"].value_counts().items():
            taxonomy_counts[t] = taxonomy_counts.get(t, 0) + c
        for fm, c in f["form"].value_counts().items():
            form_counts[fm] = form_counts.get(fm, 0) + c
        for fp, c in f["fp"].value_counts().items():
            fp_counts[fp] = fp_counts.get(fp, 0) + c

        logger.info(f"  chunk {i + 1}: scanned {total:,}, kept {kept:,}")

    logger.info(f"total raw fact rows:        {total:,}")
    logger.info(f"after fact_financial filter:{kept:,}  ({kept / total:.1%})")
    logger.info(f"null start (instant facts): {null_start_raw:,}")
    logger.info(f"garbage end (>{MAX_DATE.date()}): {garbage_end:,}")
    logger.info(f"dim_concept (taxonomy, concept) distinct: {len(concept_counts):,}")
    logger.info(f"dim_period (start, end) distinct:         {len(period_keys):,}")
    logger.info(f"taxonomy breakdown:\n{pd.Series(taxonomy_counts).sort_values(ascending=False).to_string()}")
    logger.info(f"unit breakdown:\n{pd.Series(unit_counts).sort_values(ascending=False).to_string()}")
    logger.info(f"form breakdown:\n{pd.Series(form_counts).sort_values(ascending=False).to_string()}")
    logger.info(f"fp breakdown:\n{pd.Series(fp_counts).sort_values(ascending=False).to_string()}")

    top = pd.Series(concept_counts).sort_values(ascending=False).head(40)
    logger.info("top 40 concepts (by row count, for dim_concept whitelist):")
    for (tax, con), n in top.items():
        logger.info(f"  {n:>10,}  {tax:<10}  {con}")

    revenue_like = [
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueNet",
        "SalesRevenueGoodsNet",
    ]
    logger.info("revenue-like concept hit counts:")
    for r in revenue_like:
        n = sum(v for (t, c), v in concept_counts.items() if c == r)
        logger.info(f"  {n:>10,}  {r}")


# --- Runner ---


def run(config: Config, logger: AppLogger):
    logger.info("Started diag_temp")
    _ = EdgarClient(config, logger)
    _companies(config, logger)
    _filings(config, logger)
    _facts(config, logger)
    logger.info("Completed diag_temp")
