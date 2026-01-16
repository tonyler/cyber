"""
Links database service for reading link data from CSV.
"""

import csv
from pathlib import Path
from typing import List, Dict


class LinksDBService:
    """Service for accessing links data from CSV files."""

    def __init__(self, links_db_path: str):
        self.links_db_path = Path(links_db_path)

    def _read_csv(self) -> List[Dict]:
        """Read the links CSV file and return list of dicts."""
        if not self.links_db_path.exists():
            return []
        try:
            with self.links_db_path.open('r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                return list(reader)
        except Exception:
            return []

    def get_all_links(self) -> List[Dict]:
        """Get all links from the database."""
        return self._read_csv()

    def get_links_for_month(self, year_month: str) -> List[Dict]:
        """Get links for a specific month (format: YYYY-MM)."""
        links = self.get_all_links()
        return [l for l in links if l.get('year_month', '') == year_month]

    def get_links_for_month_and_platform(self, year_month: str, platform: str) -> List[Dict]:
        """Get links for a specific month and platform."""
        links = self.get_links_for_month(year_month)
        return [l for l in links if l.get('platform', '').lower() == platform.lower()]

    def get_link_by_url(self, url: str) -> Dict:
        """Find a link by URL."""
        for link in self.get_all_links():
            if link.get('url', '') == url:
                return link
        return {}
