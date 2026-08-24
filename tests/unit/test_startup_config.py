"""Tests for startup configuration precedence."""

from pathlib import Path

from PyQt6.QtCore import QSettings

from molkey.__main__ import initialize_registry, resolve_registry_config
from molkey.config import RegistryConfig
from molkey.infrastructure.migrations import SCHEMA_VERSION, get_schema_version


def test_saved_settings_are_used_when_environment_is_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("MOLKEY_REGISTRY_ROOT", raising=False)
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    settings.setValue("registry/root", r"\\server\share\MolKey")

    config = resolve_registry_config(settings, validate_root=False)

    assert config is not None
    assert str(config.root) == r"\\server\share\MolKey"


def test_environment_takes_precedence_over_saved_settings(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MOLKEY_REGISTRY_ROOT", r"\\environment\share\MolKey")
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    settings.setValue("registry/root", r"\\saved\share\MolKey")

    config = resolve_registry_config(settings, validate_root=False)

    assert config is not None
    assert str(config.root) == r"\\environment\share\MolKey"


def test_invalid_or_missing_configuration_returns_none(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("MOLKEY_REGISTRY_ROOT", raising=False)
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)

    assert resolve_registry_config(settings, validate_root=False) is None


def test_initialize_registry_creates_and_migrates_database(tmp_path: Path) -> None:
    config = RegistryConfig.from_root(tmp_path, test_mode=True)

    initialize_registry(config)

    assert config.database_path.exists()
    assert get_schema_version(config.database_path) == SCHEMA_VERSION
    assert config.locks_dir.is_dir()
