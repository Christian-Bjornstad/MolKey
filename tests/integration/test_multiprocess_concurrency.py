"""Integration tests for multi-process concurrent writes to the registry.

These tests spawn real OS processes (spawn context, matching Windows) that all
write through the full stack — PatientKeyService, writer lock, BEGIN IMMEDIATE —
against one database, mirroring several colleagues using MolKey at once.
"""

import multiprocessing as mp
import sqlite3
from pathlib import Path

from molkey.application.patient_key_service import PatientKeyService
from molkey.infrastructure.database import connect
from molkey.infrastructure.migrations import migrate

WORKER_TIMEOUT_SECONDS = 120


def _unique_writer(db_path: Path, worker: int, count: int, queue: mp.Queue) -> None:  # type: ignore[type-arg]
    """Each process creates its own batch of unique patient IDs."""
    service = PatientKeyService(db_path)
    initials = ["AB", "CD", "EF", "GH"][worker % 4]
    keys: list[str] = []
    errors: list[str] = []
    for index in range(count):
        patient_id = f"26OUM{worker:02d}{index:05d}"
        try:
            record = service.get_or_create(patient_id, initials)
            keys.append(record.pseudonymous_key)
        except Exception as exc:  # pragma: no cover - surfaced via queue on failure
            errors.append(f"{type(exc).__name__}: {exc}")
    queue.put({"worker": worker, "keys": keys, "errors": errors})


def _mixed_case_writer(db_path: Path, variant: str, queue: mp.Queue) -> None:  # type: ignore[type-arg]
    """One process writes the same ID in a different case spelling, repeatedly."""
    service = PatientKeyService(db_path)
    keys: list[str] = []
    errors: list[str] = []
    for _ in range(5):
        try:
            record = service.get_or_create(variant, "MIX")
            keys.append(record.pseudonymous_key)
        except Exception as exc:  # pragma: no cover - surfaced via queue on failure
            errors.append(f"{type(exc).__name__}: {exc}")
    queue.put({"variant": variant, "keys": keys, "errors": errors})


def _spawn_and_collect(targets: list[tuple[object, tuple]]) -> list[dict[str, object]]:  # type: ignore[type-arg]
    context = mp.get_context("spawn")
    queue: mp.Queue = context.Queue()
    processes = []
    for target, args in targets:
        processes.append(context.Process(target=target, args=(*args, queue)))
    for process in processes:
        process.start()
    results: list[dict[str, object]] = [queue.get(timeout=WORKER_TIMEOUT_SECONDS) for _ in processes]
    for process in processes:
        process.join(timeout=WORKER_TIMEOUT_SECONDS)
    assert all(process.exitcode == 0 for process in processes), [
        process.exitcode for process in processes
    ]
    return results


def test_concurrent_processes_write_without_loss(tmp_path: Path) -> None:
    db_path = tmp_path / "registry.db"
    migrate(db_path)

    workers = 3
    writes_per_worker = 10
    results = _spawn_and_collect(
        [(_unique_writer, (db_path, worker, writes_per_worker)) for worker in range(workers)]
    )

    all_errors = [error for result in results for error in result["errors"]]
    assert not all_errors, all_errors

    conn = connect(db_path)
    try:
        stored = int(conn.execute("SELECT COUNT(*) FROM patient_keys").fetchone()[0])
        integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
    finally:
        conn.close()

    assert stored == workers * writes_per_worker
    assert integrity == "ok"


def test_concurrent_mixed_case_writes_share_one_row(tmp_path: Path) -> None:
    """26oum12345 / 26OUM12345 / 26Oum12345 from parallel processes = one key."""
    db_path = tmp_path / "registry.db"
    migrate(db_path)

    variants = ["26oum12345", "26OUM12345", "26Oum12345"]
    results = _spawn_and_collect([(_mixed_case_writer, (db_path, variant)) for variant in variants])

    all_errors = [error for result in results for error in result["errors"]]
    assert not all_errors, all_errors

    all_keys = {key for result in results for key in result["keys"]}
    assert len(all_keys) == 1, f"mixed-case variants produced different keys: {all_keys}"

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT patient_id, pseudonymous_key FROM patient_keys").fetchall()
    finally:
        conn.close()

    assert len(rows) == 1
    assert rows[0][0] == "26OUM12345", f"stored as {rows[0][0]!r}, expected canonical upper case"
    assert rows[0][1] in all_keys
