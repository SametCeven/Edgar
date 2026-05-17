import json
import time
from pathlib import Path
import requests
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
from edgar.config import Config
from edgar.shared import AppLogger


class EdgarClient:

    def __init__(self, config: Config, logger: AppLogger):
        self.config = config
        self.logger = logger
        self.min_interval = config.edgar_rate_limit_sec
        self._last_request_ts: float = 0.0

        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": config.edgar_user_agent,
                "Accept-Encoding": "gzip, deflate",
            }
        )

        # Cache subdirs
        self.cache_tickers = config.cache_tickers_dir
        self.cache_submissions = config.cache_submissions_dir
        self.cache_companyfacts = config.cache_companyfacts_dir

    # --- Public API ---

    def get_company_tickers(self, use_cache: bool = True) -> dict:
        cache_file = self.cache_tickers / "company_tickers.json"
        return self._get(
            url=self.config.edgar_base_company_tickers,
            cache_file=cache_file,
            use_cache=use_cache,
        )

    def get_submissions(self, cik: int, use_cache: bool = True) -> dict:
        padded = self._pad_cik(cik)
        url = f"{self.config.edgar_base_submissions}/CIK{padded}.json"
        cache_file = self.cache_submissions / f"CIK{padded}.json"
        return self._get(url=url, cache_file=cache_file, use_cache=use_cache)

    def get_company_facts(self, cik: int, use_cache: bool = True) -> dict:
        padded = self._pad_cik(cik)
        url = f"{self.config.edgar_base_companyfacts}/CIK{padded}.json"
        cache_file = self.cache_companyfacts / f"CIK{padded}.json"
        return self._get(url=url, cache_file=cache_file, use_cache=use_cache)

    # --- Internal ---

    @staticmethod
    def _pad_cik(cik: int) -> str:
        return str(cik).zfill(10)

    def _rate_limit(self):
        elapsed = time.monotonic() - self._last_request_ts
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last_request_ts = time.monotonic()

    def _get(self, url: str, cache_file: Path, use_cache: bool) -> dict:
        if use_cache and cache_file.exists():
            self.logger.debug(f"Cache hit: {cache_file.name}")
            with cache_file.open("r", encoding="utf-8") as f:
                return json.load(f)

        data = self._fetch(url)

        tmp = cache_file.with_suffix(cache_file.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f)
        tmp.replace(cache_file)

        return data

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        retry=retry_if_exception_type((requests.RequestException,)),
        reraise=True,
    )
    def _fetch(self, url: str) -> dict:
        self._rate_limit()
        self.logger.debug(f"GET {url}")
        resp = self.session.get(url, timeout=30)
        resp.raise_for_status()
        return resp.json()
