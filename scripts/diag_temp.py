import json
from collections import Counter
from edgar.config import Config
from edgar.shared import AppLogger, EdgarClient


SAMPLE_CIK = 320193  # AAPL
TOP_CONCEPTS = 60
DEEP_DIVE_CONCEPTS = (
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
)


# --- Phase A: single-company shape ---


def _inspect_submissions(logger: AppLogger, client: EdgarClient, cik: int):
    logger.info(f"=== SUBMISSIONS SHAPE — CIK {cik} ===")
    subs = client.get_submissions(cik)

    logger.info(f"top-level keys: {sorted(subs.keys())}")

    filings = subs.get("filings", {})
    logger.info(f"filings keys: {sorted(filings.keys())}")

    recent = filings.get("recent", {})
    logger.info(f"recent keys ({len(recent)}): {sorted(recent.keys())}")

    if recent:
        first_array = next(iter(recent.values()))
        n = len(first_array)
        logger.info(f"recent array length: {n}")

        sample = {k: v[0] for k, v in recent.items() if v}
        logger.info(f"sample filing[0] (zipped): {json.dumps(sample)[:600]}")

        forms = Counter(recent.get("form", []))
        logger.info(f"top 10 forms: {forms.most_common(10)}")

        dates = recent.get("filingDate", [])
        if dates:
            logger.info(f"filingDate range: {min(dates)} → {max(dates)}")

    files = filings.get("files", [])
    logger.info(f"overflow files: {len(files)}")
    for f in files[:3]:
        logger.info(
            f"  - {f.get('name')} | {f.get('filingCount')} filings | "
            f"{f.get('filingFrom')} → {f.get('filingTo')}"
        )


def _inspect_companyfacts(logger: AppLogger, client: EdgarClient, cik: int):
    logger.info(f"=== COMPANYFACTS SHAPE — CIK {cik} ===")
    cf = client.get_company_facts(cik)

    logger.info(f"top-level keys: {sorted(cf.keys())}")
    logger.info(f"cik={cf.get('cik')}, entityName={cf.get('entityName')}")

    facts = cf.get("facts", {})
    logger.info(f"taxonomies: {sorted(facts.keys())}")
    for tax, concepts in facts.items():
        logger.info(f"  {tax}: {len(concepts)} concepts")

    if "us-gaap" in facts:
        sample = sorted(facts["us-gaap"].keys())[:10]
        logger.info(f"us-gaap first 10 (alpha): {sample}")
    if "dei" in facts:
        logger.info(f"dei concepts (full): {sorted(facts['dei'].keys())}")

    for concept in DEEP_DIVE_CONCEPTS:
        if "us-gaap" in facts and concept in facts["us-gaap"]:
            _inspect_concept(logger, facts["us-gaap"][concept], f"us-gaap.{concept}")
            break


def _inspect_concept(logger: AppLogger, node: dict, name: str):
    logger.info(f"--- CONCEPT DEEP DIVE: {name} ---")
    logger.info(f"keys: {sorted(node.keys())}")
    logger.info(f"label: {node.get('label')}")

    units = node.get("units", {})
    logger.info(f"unit keys: {sorted(units.keys())}")
    for unit, entries in units.items():
        logger.info(f"  '{unit}': {len(entries)} entries")

    primary = next(iter(units), None)
    if not primary or not units[primary]:
        return
    entries = units[primary]

    logger.info(f"sample entry [0]: {json.dumps(entries[0])}")
    logger.info(f"sample entry [-1]: {json.dumps(entries[-1])}")

    logger.info(f"forms in '{primary}': {dict(Counter(e.get('form') for e in entries))}")
    logger.info(f"fp values in '{primary}': {dict(Counter(e.get('fp') for e in entries))}")

    by_end: dict[str, set[str]] = {}
    for e in entries:
        by_end.setdefault(e.get("end"), set()).add(e.get("accn"))
    restated = {end: accns for end, accns in by_end.items() if len(accns) > 1}
    logger.info(f"distinct end periods: {len(by_end)}; restated (>1 accn): {len(restated)}")
    if restated:
        end0 = next(iter(restated))
        logger.info(f"sample restated end={end0}: {len(restated[end0])} accns → {sorted(restated[end0])}")


# --- Phase B: cross-company scan ---


def _scan_all(logger: AppLogger, config: Config, top_n: int):
    logger.info("=== CROSS-COMPANY SCAN — all cached companyfacts ===")

    concept_companies: Counter = Counter()  # us-gaap concept → # companies reporting
    units: Counter = Counter()
    forms: Counter = Counter()
    fps: Counter = Counter()
    min_end: str | None = None
    max_end: str | None = None
    total_facts = 0
    total_companies = 0

    for path in sorted(config.cache_companyfacts_dir.glob("CIK*.json")):
        try:
            with path.open("r", encoding="utf-8") as f:
                cf = json.load(f)
        except Exception as e:
            logger.warning(f"failed to load {path.name}: {e}")
            continue
        total_companies += 1

        cf_facts = cf.get("facts", {})

        for concept in cf_facts.get("us-gaap", {}).keys():
            concept_companies[concept] += 1

        for tax in ("us-gaap", "dei"):
            for node in cf_facts.get(tax, {}).values():
                for unit, entries in node.get("units", {}).items():
                    units[unit] += len(entries)
                    for e in entries:
                        forms[e.get("form")] += 1
                        fps[e.get("fp")] += 1
                        end = e.get("end")
                        if end:
                            if min_end is None or end < min_end:
                                min_end = end
                            if max_end is None or end > max_end:
                                max_end = end
                        total_facts += 1

    logger.info(f"companies scanned: {total_companies}")
    logger.info(f"total fact rows (us-gaap + dei): {total_facts:,}")
    logger.info(f"end date range: {min_end} → {max_end}")
    logger.info(f"top 10 units (by # rows): {units.most_common(10)}")
    logger.info(f"top 15 forms (by # rows): {forms.most_common(15)}")
    logger.info(f"fp values (by # rows): {dict(fps)}")
    logger.info(f"unique us-gaap concepts: {len(concept_companies)}")
    logger.info(f"top {top_n} us-gaap concepts (by # companies reporting):")
    for concept, n in concept_companies.most_common(top_n):
        logger.info(f"  {n:4d}/{total_companies}  {concept}")


# --- Runner ---


def run(config: Config, logger: AppLogger):
    logger.info("diag_temp: JSON shape + cross-company concept/unit/form scan")
    client = EdgarClient(config, logger)
    _inspect_submissions(logger, client, SAMPLE_CIK)
    _inspect_companyfacts(logger, client, SAMPLE_CIK)
    _scan_all(logger, config, top_n=TOP_CONCEPTS)
    logger.info("diag_temp: done")
