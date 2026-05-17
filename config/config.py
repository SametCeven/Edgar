import os
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def _required(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise RuntimeError(f"Missing required env var: {key}")
    return val


@dataclass(frozen=True)
class Config:
    # EDGAR
    edgar_user_agent: str = field(default_factory=lambda: _required("EDGAR_USER_AGENT"))
    edgar_base_company_tickers: str = "https://www.sec.gov/files/company_tickers.json"
    edgar_base_submissions: str = "https://data.sec.gov/submissions"
    edgar_base_companyfacts: str = "https://data.sec.gov/api/xbrl/companyfacts"
    edgar_rate_limit_per_sec: int = 10
    edgar_retry_attempts: int = 5

    # GCP
    gcp_project_id: str = field(default_factory=lambda: _required("GCP_PROJECT_ID"))
    bq_location: str = field(default_factory=lambda: os.getenv("BQ_LOCATION", "EU"))

    # Paths
    project_root: Path = PROJECT_ROOT
    cache_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "data" / "edgar_cache")
    log_dir: Path = PROJECT_ROOT / "logs"

    # Logging
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "DEBUG"))
    log_max_files: int = 60
    
    def __post_init__(self):
        self.cache_dir.mkdir(parents=True, exist_ok=True)


