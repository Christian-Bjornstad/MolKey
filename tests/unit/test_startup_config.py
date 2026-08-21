"""Tests for startup configuration precedence."""

from pathlib import Path

from PyQt6.QtCore import QSettings

from molvault.__main__ import resolve_registry_config


def test_saved_settings_are_used_when_environment_is_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("MOLVAULT_REGISTRY_ROOT", raising=False)
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    settings.setValue("registry/root", r"\\server\share\MolVault")

    config = resolve_registry_config(settings, validate_root=False)

    assert config is not None
    assert str(config.root) == r"\\server\share\MolVault"


def test_environment_takes_precedence_over_saved_settings(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MOLVAULT_REGISTRY_ROOT", r"\\environment\share\MolVault")
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    settings.setValue("registry/root", r"\\saved\share\MolVault")

    config = resolve_registry_config(settings, validate_root=False)

    assert config is not None
    assert str(config.root) == r"\\environment\share\MolVault"


def test_invalid_or_missing_configuration_returns_none(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("MOLVAULT_REGISTRY_ROOT", raising=False)
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)

    assert resolve_registry_config(settings, validate_root=False) is None
