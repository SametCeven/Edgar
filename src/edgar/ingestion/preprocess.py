import csv
import openpyxl
from pathlib import Path
from edgar.config import Config
from edgar.shared import AppLogger, EdgarClient


# reads from edgar api, returns dict of dicts
# "AAPL": {"cik": "0000320193", "name": "Apple Inc."},
# "MSFT": {"cik": "0000789019", "name": "Microsoft Corp"},
def _get_company_tickers(logger: AppLogger, client: EdgarClient) -> dict[str, dict]:
    raw = client.get_company_tickers()
    ticker_lookup = {
        v["ticker"].upper(): {
            "cik": str(v["cik_str"]).zfill(10),
            "name": v["title"],
        }
        for v in raw.values()
    }
    logger.info(f"EDGAR ticker map: {len(ticker_lookup)} tickers")
    return ticker_lookup


# reads local .xlsx file, drops non-equity / cash rows
# returns list of dict
# {"ticker": "AAPL", "name": "APPLE INC", "sector": "Information Technology"},
# {"ticker": "MSFT", "name": "MICROSOFT CORP", "sector": "Information Technology"},
def _parse_russel_1000_xlsx(logger: AppLogger, xlsx_path: Path) -> list[dict]:
    logger.info(f"Reading {xlsx_path.name}")
    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    ws = wb.active

    rows = ws.iter_rows(values_only=True)
    headers = [str(h).strip() if h else "" for h in next(rows)]
    col = {h: i for i, h in enumerate(headers)}

    required = ("Ticker", "Name", "Sector", "Asset Class")
    missing = [h for h in required if h not in col]
    if missing:
        raise RuntimeError(f"Missing columns in xlsx: {missing}")

    out: list[dict] = []
    for row in rows:
        if not row:
            continue
        ticker = (str(row[col["Ticker"]]) if row[col["Ticker"]] else "").strip().upper()
        asset_class = (
            (str(row[col["Asset Class"]]) if row[col["Asset Class"]] else "")
            .strip()
            .lower()
        )
        if not ticker or ticker in ("-", "--", "USD", "CASH"):
            continue
        if asset_class and asset_class != "equity":
            continue
        out.append(
            {
                "ticker": ticker,
                "name": (str(row[col["Name"]]) if row[col["Name"]] else "").strip(),
                "sector": (
                    str(row[col["Sector"]]) if row[col["Sector"]] else ""
                ).strip(),
            }
        )
    wb.close()
    logger.info(f"Parsed {len(out)} equity holdings from IWB")
    return out


# helper for _join_edgar_russel
# normalizes tickers
# some tickers differ for ishares and edgar
# Berkshire Hathaway B => ishares(BRKB) edgar(BRK-B)
def _ticker_candidates(t: str) -> list[str]:
    variants = {t, t.replace(".", "-")}
    if len(t) > 1 and t[-1].isalpha() and "-" not in t and "." not in t:
        variants.add(f"{t[:-1]}-{t[-1]}")
    return list(variants)


# join russel 1000 xlsx output to edgar company tickers output to get ticker + cik
def _join_edgar_russel(
    logger: AppLogger,
    russel_1000_tickers_list: list[dict],
    ticker_lookup: dict[str, dict],
) -> tuple[list[dict], list[dict]]:
    matched: list[dict] = []
    unmatched: list[dict] = []
    seen_ciks: set[str] = set()
    for r in russel_1000_tickers_list:
        hit = next(
            (c for c in _ticker_candidates(r["ticker"]) if c in ticker_lookup), None
        )
        if not hit:
            unmatched.append(r)
            continue
        info = ticker_lookup[hit]
        if info["cik"] in seen_ciks:
            continue
        seen_ciks.add(info["cik"])
        matched.append(
            {
                "cik": info["cik"],
                "ticker": hit,
                "name": r["name"],
                "sector": r["sector"],
                "sec_name": info["name"],
            }
        )
    logger.info(f"Joined: {len(matched)} matched, {len(unmatched)} unmatched")
    return matched, unmatched


# write joined tuple to csv
def _write_company_1000(
    config: Config,
    logger: AppLogger,
    matched: list[dict],
    unmatched: list[dict],
) -> None:
    out_path = config.company_1000_csv_path
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f, fieldnames=["cik", "ticker", "name", "sector", "sec_name"]
        )
        w.writeheader()
        w.writerows(matched)
    logger.info(f"Wrote {len(matched)} companies → {out_path}")

    if unmatched:
        unmatched_path = config.company_remaining_csv_path
        with unmatched_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["ticker", "name", "sector"])
            w.writeheader()
            w.writerows(unmatched)
        logger.warning(
            f"{len(unmatched)} IWB tickers had no EDGAR match → {unmatched_path}"
        )


# runner
def run(config: Config, logger: AppLogger, client: EdgarClient):
    logger.info("preprocess: build company_1000.csv")
    ticker_lookup = _get_company_tickers(logger, client)
    russel_1000_tickers_list = _parse_russel_1000_xlsx(
        logger, config.russel_1000_xlsx_path
    )
    matched, unmatched = _join_edgar_russel(
        logger, russel_1000_tickers_list, ticker_lookup
    )
    _write_company_1000(config, logger, matched, unmatched)
