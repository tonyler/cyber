import sys
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import urlparse
import re

from google.oauth2 import service_account
from googleapiclient.discovery import build

project_root = Path(__file__).parent.parent
dashboard_dir = project_root / "dashboard"
sys.path.insert(0, str(dashboard_dir))

from logger_config import setup_logger

logger = setup_logger(__name__)


class SheetStatsUpdater:
    def __init__(self, credentials_file: str, spreadsheet_id: str, config: Optional[Dict] = None) -> None:
        self.credentials_file = credentials_file
        self.spreadsheet_id = spreadsheet_id
        self.config = config or {}
        self.sheets_service = self._init_sheets_service()

    def _init_sheets_service(self):
        credentials = service_account.Credentials.from_service_account_file(
            self.credentials_file,
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        return build("sheets", "v4", credentials=credentials)

    def _month_tab_format(self) -> str:
        return self.config.get("sync", {}).get("month_tab_format", "MM/YY")

    def _normalize_url(self, url: str) -> str:
        if not url:
            return ""
        raw = url.strip()
        tweet_id = self._extract_x_status_id(raw)
        if tweet_id:
            return f"https://x.com/i/status/{tweet_id}"
        parsed = urlparse(raw)
        if not parsed.scheme or not parsed.netloc:
            return raw.rstrip("/")
        normalized = parsed._replace(
            scheme=parsed.scheme.lower(),
            netloc=parsed.netloc.lower(),
        )
        return normalized.geturl().rstrip("/")

    def _extract_x_status_id(self, url: str) -> Optional[str]:
        if not url:
            return None
        match = re.search(r"/status(?:es)?/(\d+)", url)
        if match:
            return match.group(1)
        return None

    def format_sheet_name(self, year_month: str) -> str:
        if not year_month:
            return ""
        if "/" in year_month:
            return year_month

        try:
            year, month = year_month.split("-", 1)
        except ValueError:
            return year_month

        fmt = self._month_tab_format()
        if fmt == "MM/YYYY":
            return f"{month.zfill(2)}/{year}"
        if fmt == "MM/YY":
            return f"{month.zfill(2)}/{year[-2:]}"

        return f"{month.zfill(2)}/{year[-2:]}"

    def find_row_by_url(self, sheet_name: str, url_col: str, url: str) -> Optional[int]:
        if not sheet_name or not url_col or not url:
            return None

        target = self._normalize_url(url)
        range_name = f"'{sheet_name}'!{url_col}:{url_col}"
        try:
            result = self.sheets_service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
            ).execute()
            values = result.get("values", [])
        except Exception as e:
            logger.warning(f"Failed to read URL column {url_col} in {sheet_name}: {e}")
            return None

        for idx, row in enumerate(values, start=1):
            if not row:
                continue
            candidate = self._normalize_url(row[0])
            if candidate and candidate == target:
                return idx
        return None

    def update_row_range(
        self,
        sheet_name: str,
        start_col: str,
        end_col: str,
        row: int,
        values: list,
    ) -> bool:
        if not sheet_name or not start_col or not end_col or not row:
            return False

        range_name = f"'{sheet_name}'!{start_col}{row}:{end_col}{row}"
        body = {"values": [values]}
        try:
            self.sheets_service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
                valueInputOption="RAW",
                body=body,
            ).execute()
            return True
        except Exception as e:
            logger.warning(f"Failed to update stats row {row} in {sheet_name}: {e}")
            return False
