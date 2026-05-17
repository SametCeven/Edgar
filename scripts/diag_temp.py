from edgar.config import Config
from edgar.shared import AppLogger, EdgarClient


def run(config: Config, logger: AppLogger):
    logger.info("diag_temp: inspect AAPL submissions overflow")

    client = EdgarClient(config, logger)
    subs = client.get_submissions(320193)  # AAPL

    recent = subs["filings"]["recent"]
    files = subs["filings"].get("files", [])

    logger.info(f"recent: {len(recent['form'])} filings")
    logger.info(
        f"recent date range: {recent['filingDate'][-1]} → {recent['filingDate'][0]}"
    )
    logger.info(f"overflow files referenced: {len(files)}")

    for f in files:
        logger.info(
            f"  - {f['name']} | {f['filingCount']} filings | "
            f"{f['filingFrom']} → {f['filingTo']}"
        )

    if not files:
        logger.info("No overflow files — recent contains the full history.")
        return

    # Fetch the first overflow file and report its shape
    first = files[0]
    logger.info(f"Fetching overflow file: {first['name']}")
