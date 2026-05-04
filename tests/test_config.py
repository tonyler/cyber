"""Tests for shared/config.py"""
import os
import sys
import pytest
from pathlib import Path
from unittest.mock import patch


def _fresh_config(monkeypatch, tmp_path, env_content=""):
    """Import config with a clean state and optional .env content."""
    # Remove cached module so load_env._loaded resets
    if "config" in sys.modules:
        del sys.modules["config"]

    env_file = tmp_path / ".env"
    if env_content:
        env_file.write_text(env_content)

    # Patch PROJECT_ROOT so config finds our tmp .env
    with patch("pathlib.Path.resolve", side_effect=lambda self: self):
        pass  # just ensure no stale state

    import config as cfg  # noqa: E402 - dynamic import intentional

    # Reset _loaded flag so tests are isolated
    cfg.load_env._loaded = False
    return cfg, env_file, tmp_path


class TestLoadEnv:
    def test_loads_simple_key_value(self, tmp_path, monkeypatch):
        env = tmp_path / ".env"
        env.write_text("FOO=bar\nBAZ=qux\n")

        monkeypatch.chdir(tmp_path)
        if "config" in sys.modules:
            del sys.modules["config"]

        # Directly test the logic by calling with env_path override
        sys.path.insert(0, str(Path(__file__).parent.parent / "shared"))
        import importlib
        import config as cfg
        cfg.load_env._loaded = False

        # Patch PROJECT_ROOT to point to tmp_path
        with patch.object(cfg, "PROJECT_ROOT", tmp_path):
            cfg.load_env._loaded = False
            monkeypatch.delenv("FOO", raising=False)
            monkeypatch.delenv("BAZ", raising=False)
            cfg.load_env()
            assert os.environ.get("FOO") == "bar"
            assert os.environ.get("BAZ") == "qux"

    def test_skips_comments_and_blanks(self, tmp_path, monkeypatch):
        env = tmp_path / ".env"
        env.write_text("# this is a comment\n\nVALID=yes\n")

        import config as cfg
        cfg.load_env._loaded = False
        monkeypatch.delenv("VALID", raising=False)

        with patch.object(cfg, "PROJECT_ROOT", tmp_path):
            cfg.load_env._loaded = False
            cfg.load_env()
            assert os.environ.get("VALID") == "yes"

    def test_strips_quotes(self, tmp_path, monkeypatch):
        env = tmp_path / ".env"
        env.write_text('QUOTED="hello world"\nSINGLE=\'world\'\n')

        import config as cfg
        cfg.load_env._loaded = False
        monkeypatch.delenv("QUOTED", raising=False)
        monkeypatch.delenv("SINGLE", raising=False)

        with patch.object(cfg, "PROJECT_ROOT", tmp_path):
            cfg.load_env._loaded = False
            cfg.load_env()
            assert os.environ.get("QUOTED") == "hello world"
            assert os.environ.get("SINGLE") == "world"

    def test_does_not_override_existing_env(self, tmp_path, monkeypatch):
        env = tmp_path / ".env"
        env.write_text("EXISTING=from_file\n")
        monkeypatch.setenv("EXISTING", "from_env")

        import config as cfg
        with patch.object(cfg, "PROJECT_ROOT", tmp_path):
            cfg.load_env._loaded = False
            cfg.load_env()
            assert os.environ.get("EXISTING") == "from_env"

    def test_missing_env_file_is_safe(self, tmp_path):
        import config as cfg
        empty_dir = tmp_path / "no_env_here"
        empty_dir.mkdir()

        with patch.object(cfg, "PROJECT_ROOT", empty_dir):
            cfg.load_env._loaded = False
            cfg.load_env()  # should not raise

    def test_load_env_only_runs_once(self, tmp_path, monkeypatch):
        env = tmp_path / ".env"
        env.write_text("ONCE_VAR=first\n")
        monkeypatch.delenv("ONCE_VAR", raising=False)

        import config as cfg
        with patch.object(cfg, "PROJECT_ROOT", tmp_path):
            cfg.load_env._loaded = False
            cfg.load_env()
            os.environ["ONCE_VAR"] = "second"
            cfg.load_env()  # should be a no-op
            assert os.environ.get("ONCE_VAR") == "second"


class TestGetEnv:
    def test_returns_env_variable(self, monkeypatch):
        monkeypatch.setenv("TEST_KEY", "test_value")
        import config as cfg
        cfg.load_env._loaded = True  # skip file load
        assert cfg.get_env("TEST_KEY") == "test_value"

    def test_returns_default_when_missing(self, monkeypatch):
        monkeypatch.delenv("MISSING_KEY", raising=False)
        import config as cfg
        cfg.load_env._loaded = True
        assert cfg.get_env("MISSING_KEY", "fallback") == "fallback"

    def test_strips_whitespace(self, monkeypatch):
        monkeypatch.setenv("PADDED", "  value  ")
        import config as cfg
        cfg.load_env._loaded = True
        assert cfg.get_env("PADDED") == "value"


class TestSpecificGetters:
    def test_discord_token_primary(self, monkeypatch):
        monkeypatch.setenv("DISCORD_TOKEN", "tok123")
        monkeypatch.delenv("KEY", raising=False)
        import config as cfg
        cfg.load_env._loaded = True
        assert cfg.discord_token() == "tok123"

    def test_discord_token_fallback_to_key(self, monkeypatch):
        monkeypatch.delenv("DISCORD_TOKEN", raising=False)
        monkeypatch.setenv("KEY", "legacy_tok")
        import config as cfg
        cfg.load_env._loaded = True
        assert cfg.discord_token() == "legacy_tok"

    def test_activity_sheet_id_fallback(self, monkeypatch):
        monkeypatch.delenv("ACTIVITY_SHEET_ID", raising=False)
        monkeypatch.setenv("SPREADSHEET_ID", "legacy_id")
        import config as cfg
        cfg.load_env._loaded = True
        assert cfg.activity_sheet_id() == "legacy_id"

    def test_flask_secret_key_warning_when_missing(self, monkeypatch):
        monkeypatch.delenv("SECRET_KEY", raising=False)
        import config as cfg
        cfg.load_env._loaded = True
        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            key = cfg.flask_secret_key()
            assert len(w) == 1
            assert "insecure" in str(w[0].message).lower()
        assert key.startswith("dev-secret")

    def test_flask_secret_key_no_warning_when_set(self, monkeypatch):
        monkeypatch.setenv("SECRET_KEY", "supersecret")
        import config as cfg
        cfg.load_env._loaded = True
        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            key = cfg.flask_secret_key()
            assert len(w) == 0
        assert key == "supersecret"
