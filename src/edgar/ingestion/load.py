import json
import pandas as pd
from edgar.config import Config
from edgar.shared import AppLogger, write_csv, write_csv_incrementally

CONFIG_MODEL = {
    "companies": {
        "source_edgar_cache_folder": "submissions",
        "output_csv": "raw_companies.csv",
        "output_cols": [
            "cik",
            "name",
            "entityType",
            "sic",
            "sicDescription",
            "category",
            "fiscalYearEnd",
            "stateOfIncorporation",
            "stateOfIncorporationDescription",
            "ein",
            "lei",
            "tickers",
            "exchanges",
            "formerNames",
        ],
    },
    "filings": {
        "source_edgar_cache_folder": "submissions",
        "output_csv": "raw_filings.csv",
        "output_cols": [
            "cik",
            "accessionNumber",
            "filingDate",
            "reportDate",
            "acceptanceDateTime",
            "form",
            "act",
            "core_type",
            "fileNumber",
            "filmNumber",
            "items",
            "primaryDocDescription",
            "primaryDocument",
            "size",
            "isXBRL",
            "isInlineXBRL",
            "isXBRLNumeric",
        ],
    },
    "company_facts": {
        "source_edgar_cache_folder": "companyfacts",
        "output_csv": "raw_company_facts.csv",
        "output_cols": [
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
            "frame",
        ],
    },
}


# parse and load companies — flatten submissions JSON top-level → raw_companies.csv
def _load_companies(config: Config, logger: AppLogger) -> None:
    logger.info("Started load companies")
    config_model = CONFIG_MODEL["companies"]
    rows = []
    for path in sorted(config.cache_submissions_dir.glob("CIK*.json")):
        cik = path.stem.removeprefix("CIK")
        try:
            with path.open("r", encoding="utf-8") as f:
                sub = json.load(f)
        except Exception as e:
            logger.error(f"submissions read failed for {cik}: {e}")
            continue
        rows.append(
            {
                "cik": cik,
                "name": sub.get("name"),
                "entityType": sub.get("entityType"),
                "sic": sub.get("sic"),
                "sicDescription": sub.get("sicDescription"),
                "category": sub.get("category"),
                "fiscalYearEnd": sub.get("fiscalYearEnd"),
                "stateOfIncorporation": sub.get("stateOfIncorporation"),
                "stateOfIncorporationDescription": sub.get(
                    "stateOfIncorporationDescription"
                ),
                "ein": sub.get("ein"),
                "lei": sub.get("lei"),
                "tickers": json.dumps(sub.get("tickers") or []),
                "exchanges": json.dumps(sub.get("exchanges") or []),
                "formerNames": json.dumps(sub.get("formerNames") or []),
            }
        )
    df = pd.DataFrame(rows, columns=config_model["output_cols"])
    write_csv(logger, config.raw_dir / config_model["output_csv"], df)
    logger.info("Completed load companies")


# parse and load submissions — zip filings.recent parallel arrays → raw_filings.csv
# overflow filings.files[] (pre-2015 for IWB constituents) is intentionally skipped
def _load_submissions(config: Config, logger: AppLogger) -> None:
    logger.info("Started load submissions")
    config_model = CONFIG_MODEL["filings"]
    rows = []
    for path in sorted(config.cache_submissions_dir.glob("CIK*.json")):
        cik = path.stem.removeprefix("CIK")
        try:
            with path.open("r", encoding="utf-8") as f:
                sub = json.load(f)
        except Exception as e:
            logger.error(f"submissions read failed for {cik}: {e}")
            continue
        recent = sub.get("filings", {}).get("recent", {})
        n = len(recent.get("accessionNumber", []))
        if not n:
            continue
        for i in range(n):
            rows.append(
                {
                    "cik": cik,
                    "accessionNumber": recent["accessionNumber"][i],
                    "filingDate": recent["filingDate"][i],
                    "reportDate": recent["reportDate"][i],
                    "acceptanceDateTime": recent["acceptanceDateTime"][i],
                    "form": recent["form"][i],
                    "act": recent["act"][i],
                    "core_type": recent["core_type"][i],
                    "fileNumber": recent["fileNumber"][i],
                    "filmNumber": recent["filmNumber"][i],
                    "items": recent["items"][i],
                    "primaryDocDescription": recent["primaryDocDescription"][i],
                    "primaryDocument": recent["primaryDocument"][i],
                    "size": recent["size"][i],
                    "isXBRL": recent["isXBRL"][i],
                    "isInlineXBRL": recent["isInlineXBRL"][i],
                    "isXBRLNumeric": recent["isXBRLNumeric"][i],
                }
            )
    df = pd.DataFrame(rows, columns=config_model["output_cols"])
    write_csv(logger, config.raw_dir / config_model["output_csv"], df)
    logger.info("Completed load submissions")


# parse and load company facts — walk facts.{taxonomy}.{concept}.units.{unit}[]
# per-CIK chunks via write_csv_incrementally (full in-memory build would peak ~10-15GB)
def _load_company_facts(config: Config, logger: AppLogger) -> None:
    logger.info("Started load company_facts")
    config_model = CONFIG_MODEL["company_facts"]
    out_path = config.raw_dir / config_model["output_csv"]
    first = True
    total = 0
    for path in sorted(config.cache_companyfacts_dir.glob("CIK*.json")):
        cik = path.stem.removeprefix("CIK")
        try:
            with path.open("r", encoding="utf-8") as f:
                cf = json.load(f)
        except Exception as e:
            logger.error(f"companyfacts read failed for {cik}: {e}")
            continue
        rows = []
        for taxonomy, concepts in cf.get("facts", {}).items():
            for concept, node in concepts.items():
                for unit, entries in node.get("units", {}).items():
                    for e in entries:
                        rows.append(
                            {
                                "cik": cik,
                                "taxonomy": taxonomy,
                                "concept": concept,
                                "unit": unit,
                                "val": e.get("val"),
                                "start": e.get("start"),
                                "end": e.get("end"),
                                "fy": e.get("fy"),
                                "fp": e.get("fp"),
                                "form": e.get("form"),
                                "filed": e.get("filed"),
                                "accn": e.get("accn"),
                                "frame": e.get("frame"),
                            }
                        )
        if not rows:
            continue
        df = pd.DataFrame(rows, columns=config_model["output_cols"])
        write_csv_incrementally(logger, out_path, df, first=first)
        first = False
        total += len(rows)
    logger.info(f"raw_company_facts: {total:,} rows total → {out_path.name}")
    logger.info("Completed load company_facts")


# runner
def run(config: Config, logger: AppLogger):
    logger.info("Started load raw")
    _load_companies(config, logger)
    _load_submissions(config, logger)
    _load_company_facts(config, logger)
    logger.info("Completed load raw")
