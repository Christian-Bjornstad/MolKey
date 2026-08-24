from pathlib import Path

import pytest

from molkey.config import ConfigError, RegistryConfig


class TestRegistryConfig:
    def test_requires_registry_root_in_production_mode(self, monkeypatch):
        monkeypatch.delenv("MOLKEY_REGISTRY_ROOT", raising=False)
        monkeypatch.delenv("MOLKEY_TEST_MODE", raising=False)

        with pytest.raises(ConfigError, match="registry root"):
            RegistryConfig.from_env()

    def test_preserves_unc_paths_exactly_during_parsing(self, monkeypatch):
        unc = r"\\hospital-secure-drive\molecular-pathology\secure-package-registry"
        monkeypatch.setenv("MOLKEY_REGISTRY_ROOT", unc)

        config = RegistryConfig.from_env(validate_root=False)

        assert str(config.root) == unc

    def test_missing_root_yields_safe_error(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MOLKEY_REGISTRY_ROOT", str(tmp_path / "nonexistent"))
        monkeypatch.setenv("MOLKEY_TEST_MODE", "1")

        with pytest.raises(ConfigError, match="accessible and writable"):
            RegistryConfig.from_env()

    def test_derives_brand_neutral_subdirectories(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MOLKEY_REGISTRY_ROOT", str(tmp_path))
        monkeypatch.setenv("MOLKEY_TEST_MODE", "1")

        config = RegistryConfig.from_env()

        assert config.database_path == tmp_path / "molkey-registry.db"
        assert config.packages_dir == tmp_path / "packages"
        assert config.staging_dir == tmp_path / "staging"
        assert config.locks_dir == tmp_path / "locks"
        assert config.backups_dir == tmp_path / "backups"

    def test_allows_local_temporary_root_only_in_test_mode(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MOLKEY_REGISTRY_ROOT", str(tmp_path))
        monkeypatch.setenv("MOLKEY_TEST_MODE", "1")

        config = RegistryConfig.from_env()

        assert config.root == Path(tmp_path)
        assert config.is_test_mode is True

    def test_rejects_local_root_in_production_mode(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MOLKEY_REGISTRY_ROOT", str(tmp_path))
        monkeypatch.delenv("MOLKEY_TEST_MODE", raising=False)

        with pytest.raises(ConfigError, match="UNC|writable|accessible"):
            RegistryConfig.from_env()

    def test_rejects_file_as_registry_root_even_in_test_mode(self, tmp_path, monkeypatch):
        registry_file = tmp_path / "not-a-directory"
        registry_file.write_text("test")
        monkeypatch.setenv("MOLKEY_REGISTRY_ROOT", str(registry_file))
        monkeypatch.setenv("MOLKEY_TEST_MODE", "1")

        with pytest.raises(ConfigError, match="directory"):
            RegistryConfig.from_env()

    def test_from_root_accepts_saved_unc_without_environment(self) -> None:
        unc = r"\\hospital-server\secure-share\MolKey"

        config = RegistryConfig.from_root(unc, validate_root=False)

        assert str(config.root) == unc
        assert config.database_path == Path(unc) / "molkey-registry.db"
        assert config.is_test_mode is False

    def test_from_root_rejects_saved_local_production_path(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="UNC|writable|accessible"):
            RegistryConfig.from_root(str(tmp_path), validate_root=False)
