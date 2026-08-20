from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class ConfigError(Exception):
    """Configuration error that is safe to show to users."""


@dataclass(frozen=True)
class RegistryConfig:
    """Immutable registry configuration. Does not create directories."""

    root: Path
    database_path: Path
    packages_dir: Path
    staging_dir: Path
    locks_dir: Path
    backups_dir: Path
    is_test_mode: bool

    @classmethod
    def from_env(cls, *, validate_root: bool = True) -> RegistryConfig:
        """Load configuration from environment variables.

        Production: requires MOLVAULT_REGISTRY_ROOT pointing to writable UNC path.
        Test: requires MOLVAULT_REGISTRY_ROOT + MOLVAULT_TEST_MODE=1 for local temporary roots.
        """
        registry_root = os.environ.get("MOLVAULT_REGISTRY_ROOT")
        test_mode = os.environ.get("MOLVAULT_TEST_MODE") == "1"

        if not registry_root:
            raise ConfigError("MOLVAULT_REGISTRY_ROOT environment variable is required for registry root")

        root = Path(registry_root)

        if not test_mode and not registry_root.startswith(("\\\\", "//")):
            raise ConfigError("Production registry root must be a UNC network path")

        # Validate writability always (test mode still validates path existence)
        if validate_root:
            if not root.exists():
                raise ConfigError(f"Registry root is not accessible and writable: {root}")
            if not root.is_dir():
                raise ConfigError(f"Registry root must be an accessible directory: {root}")
            if not os.access(root, os.W_OK):
                raise ConfigError(f"Registry root is not accessible and writable: {root}")

        return cls(
            root=root,
            database_path=root / "molvault-registry.db",
            packages_dir=root / "packages",
            staging_dir=root / "staging",
            locks_dir=root / "locks",
            backups_dir=root / "backups",
            is_test_mode=test_mode,
        )
