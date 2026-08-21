"""Qualify MolVault SQLite concurrency on the configured registry share.

This script intentionally uses non-PHI synthetic records. Run from two
workstations against the same UNC registry root before production release.
"""

import argparse
import json
import multiprocessing as mp
import time
import uuid
from pathlib import Path
from typing import Any

from molvault.infrastructure.database import connect, transaction
from molvault.infrastructure.migrations import migrate


def _writer(db_path: Path, worker: int, writes: int, result_queue: Any) -> None:
    errors: list[str] = []
    prefix = uuid.uuid4().hex[:8].upper()
    for index in range(writes):
        case_id = f"CASE-SMB-{prefix}-{worker:02d}-{index:05d}"
        try:
            with transaction(db_path) as conn:
                conn.execute(
                    "INSERT INTO cases (id, patient_id, case_number) VALUES (?, ?, ?)",
                    (case_id, f"PAT-SMB-{prefix}-{worker:02d}", f"SMB{worker:02d}{index:05d}"),
                )
        except Exception as exc:  # pragma: no cover - exercised by qualification failures
            errors.append(f"{type(exc).__name__}: {exc}")
    result_queue.put({"worker": worker, "errors": errors})


def qualify(root: Path, *, workers: int = 4, writes: int = 25) -> dict[str, Any]:
    """Run multiprocess writes and database integrity checks."""
    root.mkdir(parents=True, exist_ok=True)
    db_path = root / "registry.db"
    migrate(db_path)

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
        inserted = int(conn.execute("SELECT COUNT(*) FROM cases WHERE id LIKE 'CASE-SMB-%'").fetchone()[0])
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
    parser.add_argument("registry_root", type=Path, help="Actual UNC registry root to qualify")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--writes", type=int, default=25)
    args = parser.parse_args()

    report = qualify(args.registry_root, workers=args.workers, writes=args.writes)
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
