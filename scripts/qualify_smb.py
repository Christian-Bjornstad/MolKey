"""Qualify MolKey registry concurrency on a dedicated shared test folder.

This script intentionally uses non-PHI synthetic records. Run from two
workstations against the same qualification folder before production release.
"""

import argparse
import json
import multiprocessing as mp
import time
import uuid
from pathlib import Path
from typing import Any

from molkey.application.patient_key_service import PatientKeyService
from molkey.config import REGISTRY_DB_NAME
from molkey.infrastructure.database import connect
from molkey.infrastructure.migrations import migrate
from molkey.infrastructure.registry_workbook import WORKBOOK_NAME

_MARKER_NAME = ".molkey-smb-qualification"
_MARKER_CONTENT = "MolKey synthetic SMB qualification workspace v1\n"


def _prepare_qualification_root(root: Path) -> None:
    """Prevent synthetic writes to a production registry by mistake."""
    if "qualification" not in root.name.lower():
        raise ValueError("Registry root directory name must contain 'qualification'")

    marker = root / _MARKER_NAME
    if root.exists():
        if not root.is_dir():
            raise ValueError("Qualification root must be a directory")
        if marker.exists():
            if not marker.is_file() or marker.read_text(encoding="utf-8") != _MARKER_CONTENT:
                raise ValueError("Invalid dedicated qualification marker")
            allowed = {_MARKER_NAME, REGISTRY_DB_NAME, f"{REGISTRY_DB_NAME}-journal", "locks", WORKBOOK_NAME}
            unexpected = {entry.name for entry in root.iterdir()} - allowed
            if unexpected:
                raise ValueError("Qualification root has unexpected content; use a dedicated qualification directory")
            return
        if any(root.iterdir()):
            raise ValueError("Existing registry or files found; use an empty dedicated qualification directory")
    else:
        root.mkdir(parents=True)
    marker.write_text(_MARKER_CONTENT, encoding="utf-8")


def _writer(db_path: Path, worker: int, writes: int, result_queue: Any) -> None:
    errors: list[str] = []
    prefix = uuid.uuid4().hex[:8].upper()
    service = PatientKeyService(db_path)
    for index in range(writes):
        patient_id = f"PATSMB{prefix}{worker:02d}{index:05d}"
        try:
            service.get_or_create(patient_id, initials="SMB")
            if service.workbook_error:
                errors.append(f"Excel refresh failed after {patient_id}: {service.workbook_error}")
        except Exception as exc:  # pragma: no cover - exercised by qualification failures
            errors.append(f"{type(exc).__name__}: {exc}")
    result_queue.put({"worker": worker, "errors": errors})


def qualify(root: Path, *, workers: int = 4, writes: int = 25) -> dict[str, Any]:
    """Run multiprocess writes and database integrity checks."""
    if workers < 1 or writes < 1:
        raise ValueError("workers and writes must be positive")
    _prepare_qualification_root(root)
    db_path = root / REGISTRY_DB_NAME
    migrate(db_path)
    conn = connect(db_path)
    try:
        other_patients = int(
            conn.execute("SELECT COUNT(*) FROM patient_keys WHERE patient_id NOT LIKE 'PATSMB%'").fetchone()[0]
        )
        other_cases = int(conn.execute("SELECT COUNT(*) FROM cases WHERE id NOT LIKE 'CASE-SMB-%'").fetchone()[0])
        if other_patients or other_cases:
            raise ValueError("Qualification registry contains non-synthetic records; use a dedicated test folder")
    finally:
        conn.close()

    context = mp.get_context("spawn")
    result_queue = context.Queue()
    processes = [
        context.Process(target=_writer, args=(db_path, worker, writes, result_queue)) for worker in range(workers)
    ]

    started = time.perf_counter()
    for process in processes:
        process.start()
    results = [result_queue.get(timeout=120) for _ in processes]
    for process in processes:
        process.join(timeout=120)
    elapsed = time.perf_counter() - started

    exit_codes = [process.exitcode for process in processes]
    errors = [error for result in results for error in result["errors"]]
    conn = connect(db_path)
    try:
        integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        inserted = int(conn.execute("SELECT COUNT(*) FROM patient_keys WHERE patient_id LIKE 'PATSMB%'").fetchone()[0])
        journal_mode = str(conn.execute("PRAGMA journal_mode").fetchone()[0]).upper()
    finally:
        conn.close()

    expected = workers * writes
    passed = not errors and all(code == 0 for code in exit_codes) and integrity == "ok" and inserted >= expected
    return {
        "passed": passed,
        "registry_root": str(root),
        "workers": workers,
        "writes_per_worker": writes,
        "expected_writes": expected,
        "observed_synthetic_rows": inserted,
        "integrity_check": integrity,
        "journal_mode": journal_mode,
        "worker_exit_codes": exit_codes,
        "errors": errors,
        "elapsed_seconds": round(elapsed, 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("registry_root", type=Path, help="Dedicated qualification folder on the intended SMB share")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--writes", type=int, default=25)
    args = parser.parse_args()

    report = qualify(args.registry_root, workers=args.workers, writes=args.writes)
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
