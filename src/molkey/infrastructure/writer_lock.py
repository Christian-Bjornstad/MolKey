"""Application-level writer lock for SQLite on shared drives.

Uses portalocker for cross-process locking on the registry.lock file.
This is defense in depth, not a replacement for SQLite transactions.
"""

import contextlib
from collections.abc import Iterator
from contextlib import suppress
from pathlib import Path
from typing import Any, Literal

try:
    import portalocker
except ImportError:  # pragma: no cover
    portalocker = None  # type: ignore[assignment]


class RegistryBusyError(Exception):
    """Raised when writer lock cannot be acquired within timeout."""

    pass


class WriterLock:
    """File-based writer lock for registry database.

    Lock file: {registry_root}/locks/registry.writer.lock
    Uses portalocker for cross-process coordination.
    """

    def __init__(self, registry_root: Path, timeout: float = 5.0) -> None:
        self.registry_root = Path(registry_root)
        self.lock_dir = self.registry_root / "locks"
        self.lock_path = self.lock_dir / "registry.writer.lock"
        self.timeout = timeout
        self._lock: portalocker.Lock | None = None

    def acquire(self) -> None:
        """Acquire the writer lock.

        Raises:
            RegistryBusyError: If lock cannot be acquired within timeout.
            RuntimeError: If portalocker is not available.
        """
        if portalocker is None:
            raise RuntimeError("portalocker not installed")

        self.lock_dir.mkdir(parents=True, exist_ok=True)

        # NON_BLOCKING lets portalocker enforce its bounded retry timeout.
        self._lock = portalocker.Lock(
            str(self.lock_path),
            mode="w",
            timeout=self.timeout,
            check_interval=min(0.1, self.timeout) if self.timeout > 0 else 0.001,
            flags=portalocker.LOCK_EX | portalocker.LOCK_NB,
        )

        try:
            self._lock.acquire()
        except (portalocker.LockException, OSError) as e:
            self._lock = None
            raise RegistryBusyError(f"Could not acquire writer lock on {self.lock_path} within {self.timeout}s") from e

    def release(self) -> None:
        """Release the writer lock."""
        if self._lock is not None:
            with suppress(Exception):
                self._lock.release()
            self._lock = None

    def __enter__(self) -> "WriterLock":
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> Literal[False]:
        self.release()
        return False


@contextlib.contextmanager
def writer_lock(registry_root: Path, timeout: float = 5.0) -> Iterator[None]:
    """Context manager for acquiring the writer lock.

    Args:
        registry_root: Root directory of the registry (contains locks/).
        timeout: Maximum time to wait for lock in seconds.

    Yields:
        None (lock is held during context).

    Raises:
        RegistryBusyError: If lock cannot be acquired.
    """
    lock = WriterLock(registry_root, timeout)
    lock.acquire()
    try:
        yield
    finally:
        lock.release()


def get_registry_root_from_db(db_path: Path) -> Path:
    """Extract registry root from database path.

    Assumes db_path is {registry_root}/registry.db
    """
    return db_path.parent


if __name__ == "__main__":
    # Quick manual test
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        print("Testing writer lock...")
        with writer_lock(root):
            print("Lock acquired")
            # Try second acquisition (should fail quickly)
            try:
                with writer_lock(root, timeout=0.1):
                    print("Second lock acquired (unexpected)")
            except RegistryBusyError:
                print("Second lock correctly blocked")
