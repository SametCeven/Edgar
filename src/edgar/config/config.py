import os
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def _required(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise RuntimeError(f"Missing required env var: {key}")
    return val


@dataclass(frozen=True)
class Config:
    # EDGAR API
    edgar_user_agent: str = field(default_factory=lambda: _required("EDGAR_USER_AGENT"))
    edgar_base_company_tickers: str = "https://www.sec.gov/files/company_tickers.json"
    edgar_base_submissions: str = "https://data.sec.gov/submissions"
    edgar_base_companyfacts: str = "https://data.sec.gov/api/xbrl/companyfacts"
    edgar_rate_limit_sec: float = 0.5
    edgar_retry_attempts: int = 5

    # GCP
    gcp_project_id: str = field(default_factory=lambda: _required("GCP_PROJECT_ID"))
    bq_location: str = field(default_factory=lambda: os.getenv("BQ_LOCATION", "EU"))

    # Folder Paths
    project_root_dir: Path = PROJECT_ROOT
    log_dir: Path = PROJECT_ROOT / "logs"
    cache_dir: Path = PROJECT_ROOT / "data" / "edgar_cache"
    cache_preprocess_dir: Path = PROJECT_ROOT / "data" / "edgar_cache" / "preprocess"
    cache_tickers_dir: Path = PROJECT_ROOT / "data" / "edgar_cache" / "tickers"
    cache_submissions_dir: Path = PROJECT_ROOT / "data" / "edgar_cache" / "submissions"
    cache_companyfacts_dir: Path = (
        PROJECT_ROOT / "data" / "edgar_cache" / "companyfacts"
    )

    # Fİle Paths
    russel_1000_xls_path: Path = (
        PROJECT_ROOT / "data" / "russel_1000" / "iShares-Russell-1000-ETF_fund.xls"
    )
    company_1000_csv_path: Path = (
        PROJECT_ROOT / "data" / "edgar_cache" / "preprocess" / "company_1000.csv"
    )
    company_remaining_csv_path: Path = (
        PROJECT_ROOT / "data" / "edgar_cache" / "preprocess" / "company_remaining.csv"
    )

    # Logging
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "DEBUG"))
    log_max_files: int = 60

    def __post_init__(self):
        for d in (
            self.cache_dir,
            self.cache_preprocess_dir,
            self.cache_tickers_dir,
            self.cache_submissions_dir,
            self.cache_companyfacts_dir,
            self.log_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)
