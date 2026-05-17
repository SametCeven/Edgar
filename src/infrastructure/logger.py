import logging
from pathlib import Path
from datetime import datetime

LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


class AppLogger:
    def __init__(
        self,
        level_str: str = "DEBUG",
        log_dir: Path = Path("/logs"),
        max_files: int = 60,
    ):
        self.log_path = log_dir
        self.log_path.mkdir(parents=True, exist_ok=True)

        # Create unique log file per run
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.log_file = self.log_path / f"run_{timestamp}.log"

        self.logger = logging.getLogger(f"app_logger_{timestamp}")
        level_int = LOG_LEVELS.get(level_str.upper(), logging.DEBUG)
        self.logger.setLevel(level_int)
        self.logger.propagate = False

        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(message)s"
        )

        # File handler (no rotation, single file per run)
        file_handler = logging.FileHandler(self.log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)

        # Console handler (optional but useful)
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)

        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)

        # Cleanup old logs
        self._cleanup_old_logs(max_files)

    # --- Public API ---
    def info(self, msg: str):
        self.logger.info(msg)

    def warning(self, msg: str):
        self.logger.warning(msg)

    def error(self, msg: str):
        self.logger.error(msg)

    def debug(self, msg: str):
        self.logger.debug(msg)

    def exception(self, msg: str):
        self.logger.exception(msg)

    # --- Internal ---
    def _cleanup_old_logs(self, max_files: int):
        log_files = sorted(
            self.log_path.glob("run_*.log"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )

        for old_file in log_files[max_files:]:
            try:
                old_file.unlink()
            except Exception:
                pass  # don't crash logging if cleanup fails