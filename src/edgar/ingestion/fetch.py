import csv
from edgar.config import Config
from edgar.shared import AppLogger, EdgarClient


# read company_1000.csv → list of {cik, ticker, name, sector, sec_name}
def _read_company_1000(logger: AppLogger, config: Config) -> list[dict]:
    with config.company_1000_csv_path.open("r", encoding="utf-8") as f:
        companies = list(csv.DictReader(f))
    logger.info(f"Loaded {len(companies)} companies from company_1000.csv")
    return companies


# fetch submissions + companyfacts for one company
# returns list of failure dicts (empty if both ok)
def _fetch_one(
    logger: AppLogger,
    client: EdgarClient,
    row: dict,
    idx: int,
    total: int,
) -> list[dict]:
    cik_str = row["cik"]
    ticker = row["ticker"]
    cik_int = int(cik_str)
    logger.debug(f"[{idx}/{total}] {ticker} (CIK {cik_str})")

    failures: list[dict] = []
    for endpoint, fn in (
        ("submissions", client.get_submissions),
        ("companyfacts", client.get_company_facts),
    ):
        try:
            fn(cik_int, use_cache=False)
        except Exception as e:
            logger.error(f"  {endpoint} failed for {ticker}/{cik_str}: {e}")
            failures.append(
                {
                    "cik": cik_str,
                    "ticker": ticker,
                    "endpoint": endpoint,
                    "error": str(e),
                }
            )
    return failures


# fetch all companies, collect failures
def _fetch_all(
    logger: AppLogger, client: EdgarClient, companies: list[dict]
) -> list[dict]:
    total = len(companies)
    failed: list[dict] = []
    for i, row in enumerate(companies, start=1):
        failed.extend(_fetch_one(logger, client, row, i, total))
    ok = total - len({f["cik"] for f in failed})
    logger.info(f"fetch complete: {ok}/{total} ok, {len(failed)} failures")
    return failed


# write failures to csv (only if any)
def _write_failed(logger: AppLogger, config: Config, failed: list[dict]) -> None:
    if not failed:
        return
    failed_path = config.cache_preprocess_dir / "fetch_failed.csv"
    with failed_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["cik", "ticker", "endpoint", "error"])
        w.writeheader()
        w.writerows(failed)
    logger.warning(f"Wrote {len(failed)} failures → {failed_path}")


# runner
def run(config: Config, logger: AppLogger, client: EdgarClient):
    logger.info("fetch: submissions + companyfacts for company_1000")
    companies = _read_company_1000(logger, config)
    failed = _fetch_all(logger, client, companies)
    _write_failed(logger, config, failed)
