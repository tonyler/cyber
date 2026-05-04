"""Shared pytest fixtures (auto-loaded by pytest)."""
import sys
from pathlib import Path

# Make project modules importable without installing
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "shared"))
sys.path.insert(0, str(PROJECT_ROOT / "scrapers"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "dashboard3"))
sys.path.insert(0, str(PROJECT_ROOT / "tests"))
