import csv
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from edgar.config import Config
from edgar.shared import AppLogger, EdgarClient

# SpreadsheetML namespace used by iShares export
NS = {"ss": "urn:schemas-microsoft-com:office:spreadsheet"}


def _parse_iwb_holdings(xls_path: Path, logger: AppLogger) -> list[dict]:
    logger.info(f"Parsing {xls_path.name}")
    raw = xls_path.read_text(encoding="utf-8", errors="replace")
    # iShares ships malformed XML (unescaped '&' in URLs) — escape stray '&'
    cleaned = re.sub(r"&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9A-Fa-f]+);)", "&amp;", raw)
    root = ET.fromstring(cleaned)

    holdings_ws = next(
        (
            ws
            for ws in root.findall("ss:Worksheet", NS)
            if ws.get(f"{{{NS['ss']}}}Name") == "Holdings"
        ),
        None,
    )
    if holdings_ws is None:
        raise RuntimeError("Holdings worksheet not found in IWB xls")

    rows_xml = holdings_ws.find("ss:Table", NS).findall("ss:Row", NS)

    # Find header row by locating row whose first cell text is 'Ticker'
    header_idx = None
    headers: list[str] = []
    for i, row in enumerate(rows_xml):
        cells = row.findall("ss:Cell", NS)
        texts = [
            (c.find("ss:Data", NS).text if c.find("ss:Data", NS) is not None else "")
            for c in cells
        ]
        if texts and texts[0] == "Ticker":
            header_idx = i
            headers = texts
            break

    if header_idx is None:
        raise RuntimeError("Could not locate 'Ticker' header row in Holdings sheet")

    out: list[dict] = []
    for row in rows_xml[header_idx + 1 :]:
        cells = row.findall("ss:Cell", NS)
        if not cells:
            continue
        values = [
            (c.find("ss:Data", NS).text if c.find("ss:Data", NS) is not None else "")
            for c in cells
        ]
        rec = dict(zip(headers, values))
        ticker = (rec.get("Ticker") or "").strip().upper()
        asset_class = (rec.get("Asset Class") or "").strip().lower()
        if not ticker or ticker in ("-", "--", "USD", "CASH"):
            continue
        if asset_class and asset_class != "equity":
            continue  # drop cash, futures, etc.
        out.append(
            {
                "ticker": ticker,
                "name": (rec.get("Name") or "").strip(),
                "sector": (rec.get("Sector") or "").strip(),
            }
        )
    logger.info(f"Parsed {len(out)} equity holdings from IWB")
    return out


def _build_edgar_ticker_index(raw: dict) -> dict[str, dict]:
    return {
        v["ticker"].upper(): {
            "cik": str(v["cik_str"]).zfill(10),
            "name": v["title"],
        }
        for v in raw.values()
    }


def _ticker_candidates(t: str) -> list[str]:
    variants = {t, t.replace(".", "-")}
    if len(t) > 1 and t[-1].isalpha() and "-" not in t and "." not in t:
        variants.add(f"{t[:-1]}-{t[-1]}")
    return list(variants)


def run(config: Config, logger: AppLogger):
    logger.info("preprocess: build company_1000.csv")

    # 1. Parse IWB holdings
    iwb_rows = _parse_iwb_holdings(config.russel_1000_xls_path, logger)

    # 2. Fetch EDGAR ticker map (cached)
    client = EdgarClient(config, logger)
    edgar_raw = client.get_company_tickers()
    edgar_idx = _build_edgar_ticker_index(edgar_raw)
    logger.info(f"EDGAR ticker map: {len(edgar_idx)} tickers")

    # 3. Join
    matched: list[dict] = []
    unmatched: list[dict] = []
    seen_ciks: set[str] = set()
    for r in iwb_rows:
        hit = next((c for c in _ticker_candidates(r["ticker"]) if c in edgar_idx), None)
        if not hit:
            unmatched.append(r)
            continue
        info = edgar_idx[hit]
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

    # 4. Write outputs
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
