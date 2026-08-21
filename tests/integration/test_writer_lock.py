"""Integration tests for writer lock serialization."""

import tempfile
import threading
import time
from pathlib import Path

import pytest

from molvault.infrastructure.writer_lock import (
    RegistryBusyError,
    WriterLock,
    get_registry_root_from_db,
    writer_lock,
)


class TestWriterLock:
    """Test application-level writer lock for SQLite on shared drives."""

    def test_lock_acquire_release(self):
        """Lock can be acquired and released."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            lock = WriterLock(root, timeout=1.0)
            lock.acquire()
            try:
                assert lock._lock is not None
            finally:
                lock.release()
            assert lock._lock is None

    def test_context_manager(self):
        """Context manager acquires and releases lock."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with writer_lock(root, timeout=1.0):
                lock_path = root / "locks" / "registry.writer.lock"
                assert lock_path.exists()
            # Lock released after context

    def test_second_acquisition_blocks(self):
        """Second lock acquisition blocks and raises RegistryBusyError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with writer_lock(root, timeout=5.0), pytest.raises(RegistryBusyError), writer_lock(root, timeout=0.1):
                pass  # Should not reach here

    def test_lock_timeout_is_respected(self):
        """Lock acquisition respects timeout parameter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with writer_lock(root, timeout=5.0):
                start = time.time()
                with pytest.raises(RegistryBusyError), writer_lock(root, timeout=0.5):
                    pass
                elapsed = time.time() - start
                # Should have timed out around 0.5s (with some tolerance)
                assert 0.3 < elapsed < 1.5

    def test_concurrent_threads_block(self):
        """A contending thread times out while another thread holds the lock."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            acquired = threading.Event()
            release = threading.Event()
            results = []

            def holder():
                with writer_lock(root, timeout=1.0):
                    acquired.set()
                    release.wait(timeout=2.0)

            def contender():
                acquired.wait(timeout=1.0)
                try:
                    with writer_lock(root, timeout=0.2):
                        results.append("acquired")
                except RegistryBusyError:
                    results.append("busy")

            t1 = threading.Thread(target=holder)
            t2 = threading.Thread(target=contender)
            t1.start()
            t2.start()
            t2.join(timeout=2.0)
            release.set()
            t1.join(timeout=2.0)

            assert results == ["busy"]

    def test_lock_file_created_in_locks_subdirectory(self):
        """Lock file is created in locks/ subdirectory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with writer_lock(root, timeout=1.0):
                lock_path = root / "locks" / "registry.writer.lock"
                assert lock_path.exists()
                assert lock_path.parent.name == "locks"

    def test_get_registry_root_from_db(self):
        """Extract registry root from database path."""
        db_path = Path(r"\\server\share\registry\registry.db")
        root = get_registry_root_from_db(db_path)
        assert root == Path(r"\\server\share\registry")

    def test_get_registry_root_from_db_local(self):
        """Extract registry root from local database path."""
        db_path = Path("/home/user/registry/registry.db")
        root = get_registry_root_from_db(db_path)
        assert root == Path("/home/user/registry")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
