# Secure Package Registry Implementation Plan

> **For Hermes:** Implement this plan task-by-task using strict RED → GREEN → REFACTOR TDD. Do not write production behavior before observing the corresponding test fail.

**Goal:** Build a dependable, simple PyQt6 application that maps hospital patient/case identifiers to pseudonymous package IDs, encrypts large files for transfer using AES-256-GCM, and stores registry metadata in SQLite on an access-controlled hospital SMB share.

**Architecture:** Use a destination-neutral layered design: PyQt6 UI → application services → domain models/ports → SQLite, filesystem, cryptography, and Windows identity adapters. One SQLite database is the registry source of truth. Every write uses short transactions, SQLite locking plus bounded retries, and an application writer lock. Package files are built in a staging directory, verified, finalized atomically where possible, and then recorded as ready.

**Tech Stack:** Python 3.11+, `uv`, PyQt6, stdlib `sqlite3`, `cryptography`, `portalocker`, `platformdirs`, `pytest`, `pytest-qt`, `pytest-cov`, `ruff`, `mypy`, PyInstaller.

---

## 1. Scope and safety boundary

### MVP includes

- Configure and validate a secure shared registry root.
- Record minimal patient/case identifiers; patient names are excluded by default.
- Generate random, non-identifying package IDs such as `SPK-2026-8F4C2A91`.
- Generate a fresh random 256-bit data-encryption key per package.
- Encrypt arbitrarily large files by streaming; never load genomic files wholly into RAM.
- Authenticate encrypted content and package metadata.
- Store only wrapped keys, never plaintext AES keys.
- Search by patient ID, specimen ID, package ID, and optional external destination reference.
- Record safe security-relevant audit events.
- Back up and restore the SQLite database with integrity verification.
- Manually export finalized encrypted packages; BaseSpace is destination metadata only in MVP.

### Explicitly excluded from MVP

- Direct BaseSpace or other cloud APIs.
- Hospital-wide database server.
- Patient names, dates of birth, national identity numbers, or clinical notes.
- Displaying/copying raw AES keys.
- Editing the database with third-party tools.
- Generic user/password management; use the signed-in Windows identity.
- Automatic conflict merging or offline writes.

### Mandatory governance gate

This is a technical plan, not production authorization. Before real patient data is used, hospital IT/security/privacy must approve: the SMB topology and locking behavior, permissions, retention, audit policy, key custody/recovery, certificate deployment, malware scanning, backup ownership, and incident response.

---

## 2. Important design corrections

1. **SQLite over SMB is a known risk.** The application must refuse unsupported paths/configurations, use rollback journaling (`DELETE`, not WAL), short transactions, bounded retries, and tested backup/restore. A pilot concurrency and forced-disconnect test on the real hospital share is a release blocker.
2. **The writer lock is defense in depth, not a replacement for SQLite transactions.** Use `portalocker` on `{root}/locks/registry.writer.lock`, then `BEGIN IMMEDIATE`. Only this application may write to the database.
3. **Do not mark a package `Ready` before its final directory exists and verifies.** Insert it as `Finalizing`, move/finalize files, then change it to `Ready` in a second short transaction. Startup reconciliation handles crashes between those steps.
4. **AES-GCM nonces must never repeat under the same key.** Use one fresh package key and a random 96-bit nonce per file; reject duplicate nonce metadata before finalization.
5. **Do not store GCM tags separately if the file format already appends them.** Define and version one encrypted-file container format.
6. **DPAPI user/machine scope alone cannot serve different users on different computers.** Production key wrapping must use an approved shared recovery mechanism. The implementation will expose a `KeyWrapper` interface; tests use an in-memory test wrapper. The production wrapper is not accepted until the governance decision below is resolved.

---

## 3. Proposed repository structure

```text
SecurePackageRegistry/
├── .hermes/plans/
├── pyproject.toml
├── README.md
├── CHANGELOG.md
├── src/secure_package_registry/
│   ├── __init__.py
│   ├── __main__.py
│   ├── config.py
│   ├── domain/
│   │   ├── errors.py
│   │   ├── identifiers.py
│   │   ├── models.py
│   │   └── states.py
│   ├── application/
│   │   ├── case_service.py
│   │   ├── package_service.py
│   │   ├── encryption_service.py
│   │   ├── search_service.py
│   │   ├── backup_service.py
│   │   └── reconciliation_service.py
│   ├── infrastructure/
│   │   ├── database.py
│   │   ├── migrations.py
│   │   ├── repositories.py
│   │   ├── writer_lock.py
│   │   ├── encrypted_file.py
│   │   ├── key_wrapping.py
│   │   ├── filesystem.py
│   │   ├── windows_identity.py
│   │   └── audit.py
│   └── ui/
│       ├── app.py
│       ├── main_window.py
│       ├── dashboard_page.py
│       ├── create_package_page.py
│       ├── search_page.py
│       └── models.py
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── ui/
│   ├── security/
│   ├── smb/
│   └── fixtures/
├── scripts/
│   ├── initialize_registry.py
│   ├── check_registry.py
│   ├── backup_registry.py
│   └── restore_registry.py
└── packaging/
    └── secure-package-registry.spec
```

---

## 4. TDD working agreement

For every production behavior below:

1. **RED:** Add one focused test and run only that test. Confirm it fails for the expected missing behavior—not a typo/import problem.
2. **GREEN:** Add the smallest implementation that passes.
3. Run the focused test, then `uv run pytest -q`.
4. **REFACTOR:** Improve names/duplication only while tests remain green.
5. Commit the vertical slice.

Standard commands:

```bash
uv sync --dev
uv run pytest tests/path/test_file.py::test_name -vv
uv run pytest -q
uv run pytest --cov=secure_package_registry --cov-report=term-missing
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

Do not mock SQLite, encryption, or the filesystem when a temporary real resource can test the behavior. Use dependency injection only at true OS/security boundaries.

---

# 5. TDD task sequence

## Phase A — Foundation

### Task 1: Scaffold the installable project

**Files:** Create `pyproject.toml`, `src/secure_package_registry/__init__.py`, `tests/unit/test_package_metadata.py`, `.gitignore`, `README.md`.

**RED:** Test imports the package and expects a semantic `__version__`.

**Verify RED:**
```bash
uv run pytest tests/unit/test_package_metadata.py -vv
```
Expected: failure because the package/version does not exist.

**GREEN:** Add the minimal package and metadata. Configure runtime dependencies and dev tools. Pin supported Python to `>=3.11,<3.15` unless hospital packaging tests approve newer Python.

**Verify:** focused test, full suite, Ruff.

**Commit:** `chore: scaffold secure package registry`

### Task 2: Resolve and validate registry configuration

**Files:** Create `src/secure_package_registry/config.py`, `tests/unit/test_config.py`.

**RED slices:**
- `EMOLPAT_REGISTRY_ROOT` is required in production mode.
- UNC paths are preserved exactly.
- Missing/unwritable root yields a user-safe configuration error.
- Expected subdirectories are derived without embedding patient information.
- A local temporary root is allowed only in explicit test/development mode.

**GREEN:** Add immutable `RegistryConfig`; do not create folders during pure parsing.

**Commit:** `feat: validate shared registry configuration`

### Task 3: Define domain errors, states, and records

**Files:** Create `domain/errors.py`, `domain/states.py`, `domain/models.py`; test `tests/unit/domain/test_models.py`.

**RED slices:**
- Valid package transitions: `Draft → Encrypting → Verified → Finalizing → Ready → Exported`.
- `Failed` is reachable from active processing states.
- Illegal transitions, e.g. `Ready → Draft`, are rejected.
- Domain records distinguish case ID, patient ID, package ID, key ID, and destination reference.

**GREEN:** Frozen dataclasses/enums with transition validation; no database or UI imports.

**Commit:** `feat: define package workflow domain`

### Task 4: Generate non-identifying package and key IDs

**Files:** Create `domain/identifiers.py`; test `tests/unit/domain/test_identifiers.py`.

**RED slices:** format validation, injected year, uppercase random component, 10,000 generated values without collision in the test run, patient/specimen input is neither accepted nor embedded.

**GREEN:** Use `secrets`, not `random`; collision protection is also enforced by a database unique constraint.

**Commit:** `feat: generate pseudonymous identifiers`

---

## Phase B — SQLite and multi-user controls

### Task 5: Create versioned schema migration 001

**Files:** Create `infrastructure/migrations.py`, `tests/integration/test_migrations.py`.

**Schema:** `schema_version`, `cases`, `packages`, `encryption_keys`, `package_files`, `destinations`, `audit_events`. Add foreign keys, uniqueness, `CHECK` constraints for states, UTC timestamps, and search indexes.

**RED slices:** empty DB migrates to v1; second migration run is idempotent; foreign keys reject orphan rows; duplicate package/key IDs fail.

**GREEN:** Migration executes in one transaction and records version only on success.

**Commit:** `feat: add initial registry schema`

### Task 6: Enforce safe SQLite connection settings

**Files:** Create `infrastructure/database.py`; test `tests/integration/test_database_settings.py`.

**RED slices:** each connection has `foreign_keys=ON`, `journal_mode=DELETE`, `synchronous=FULL`, bounded `busy_timeout`, and explicit transaction control; connections are closed after operations.

**GREEN:** One connection factory; never hold a global GUI-lifetime connection.

**Commit:** `feat: configure sqlite for shared registry`

### Task 7: Serialize writers with bounded lock acquisition

**Files:** Create `infrastructure/writer_lock.py`; tests `tests/integration/test_writer_lock.py`.

**RED slices:** first process obtains lock; second process times out with actionable `RegistryBusyError`; lock releases after success and exception; retry uses bounded monotonic timing; lock metadata never contains PHI.

**GREEN:** Wrap `portalocker`; do not invent lock-file deletion heuristics. An old lock file is harmless if no OS lock is held.

**Commit:** `feat: serialize registry writers`

### Task 8: Add short write transactions and retry behavior

**Files:** Modify `database.py`; test `tests/integration/test_write_transactions.py`.

**RED slices:** `BEGIN IMMEDIATE`; commit success; rollback on exception; retry only lock/busy errors; no retry for constraints/programming errors; retry budget exhaustion gives a clear operator message.

**GREEN:** Context manager combines writer lock and DB transaction, with injectable delay for deterministic tests.

**Commit:** `feat: add bounded sqlite write transactions`

### Task 9: Implement repositories as vertical slices

**Files:** Create `infrastructure/repositories.py`; tests `tests/integration/test_case_repository.py`, `test_package_repository.py`, `test_file_repository.py`.

**TDD order:** create/search case → create package → transition state → attach wrapped key metadata → attach file metadata → set destination reference. One failing test and minimal implementation per slice.

**Rules:** parameterized SQL only; repository returns domain records; no UI types; audit event is added in the same transaction as the security-relevant mutation.

**Commit:** one commit per repository slice, e.g. `feat: persist package state transitions`.

### Task 10: Validate real SMB concurrency

**Files:** Create `tests/smb/test_real_share_concurrency.py`, `scripts/check_registry.py`, `docs/smb-pilot.md`.

**RED:** Mark test with `@pytest.mark.smb`; require explicit `EMOLPAT_TEST_REGISTRY_ROOT`; spawn multiple reader/writer processes; verify expected completed rows, no lost writes, `PRAGMA integrity_check='ok'`, and bounded busy errors.

**GREEN:** Add only the harness/configuration needed. Run on the actual hospital share—not a local folder masquerading as a network drive.

**Release gate:** Simulate a client process termination during a transaction and a temporary network disconnect with IT supervision. If integrity/recovery is not consistently clean, stop and revisit the no-server architecture.

**Commit:** `test: add shared drive concurrency qualification`

---

## Phase C — Cryptography and safe package format

### Task 11: Define the key-wrapping port

**Files:** Create `infrastructure/key_wrapping.py`; tests `tests/unit/test_key_wrapping_contract.py`.

**RED slices:** wrapper returns versioned `WrappedKey` containing method and key reference; unwrap round-trip in test implementation; wrong key/tampered blob fails; representations/logging never expose plaintext.

**GREEN:** Define `KeyWrapper` protocol and test-only wrapper. Do not ship the test wrapper in production startup.

**Governance decision required before Task 16:** Choose and prototype one approved production mechanism, preferably hospital certificate/KMS-backed wrapping. Document recovery on a replacement workstation and by a second authorized user. Do not use ordinary per-user DPAPI as the shared production solution.

**Commit:** `feat: define recoverable key wrapping contract`

### Task 12: Specify a versioned encrypted-file container

**Files:** Create `infrastructure/encrypted_file.py`; tests `tests/unit/test_container_format.py`; create `docs/encrypted-file-format.md`.

**Format fields:** magic bytes, format version, algorithm ID, nonce length, random 96-bit nonce, safe authenticated metadata, ciphertext with appended 128-bit GCM tag. Use fixed-width/network-byte-order fields and strict maximum header sizes.

**RED slices:** header round-trip; unknown version rejected; malformed lengths rejected before allocation; truncation rejected; original filename and patient ID absent from container bytes.

**GREEN:** Parser/serializer only—no encryption yet.

**Commit:** `feat: define encrypted file format v1`

### Task 13: Stream AES-256-GCM encryption

**Files:** Extend `encrypted_file.py`; tests `tests/security/test_stream_encryption.py`.

**RED slices:** known small plaintext round-trip; multi-chunk round-trip; 32-byte key required; fresh nonce per file; empty file supported; plaintext key not persisted; output cleanup after failure.

**GREEN:** Use `cryptography` streaming `Cipher(algorithms.AES(key), modes.GCM(nonce))`; write to a temporary file and fsync before rename. Zero local references to key buffers where practical, while documenting Python memory limitations.

**Commit:** `feat: stream authenticated file encryption`

### Task 14: Detect tampering and truncation

**Files:** Tests `tests/security/test_tamper_detection.py`; modify `encrypted_file.py`.

**RED slices:** changed ciphertext, header/AAD, nonce, tag, and truncated output all fail closed; no partial plaintext survives failed decryption.

**GREEN:** Decrypt to temporary output; finalize/rename only after tag verification.

**Commit:** `test: enforce encrypted file tamper detection`

### Task 15: Build export-safe manifests

**Files:** Create `application/encryption_service.py`; tests `tests/security/test_manifest_privacy.py`.

**RED slices:** manifest includes package ID, format versions, export names, sizes, encrypted SHA-256; excludes patient/specimen IDs, source paths, raw/wrapped key blobs, usernames, and internal DB IDs; deterministic serialization supports manifest hashing.

**GREEN:** JSON schema/version and canonical serialization. Authenticate manifest bytes as package metadata or include a signed/authenticated manifest strategy approved with the production wrapper.

**Commit:** `feat: create privacy-safe package manifests`

### Task 16: Implement the approved production key wrapper

**Files:** Add the selected adapter under `infrastructure/key_wrapping.py` (or a focused module); tests `tests/security/test_production_key_wrapper.py`; document `docs/key-recovery.md`.

**Prerequisite:** Written selection of certificate/KMS/key custody mechanism and a non-production test certificate/fixture. Never commit private keys or passwords.

**RED slices:** two authorized test identities/workstations can recover; unauthorized identity cannot; corrupted wrapped key fails; key version/thumbprint/reference stored; old package remains recoverable after key rotation; backup restore works on replacement test workstation.

**GREEN:** Implement only the approved mechanism. If the real mechanism cannot be integration-tested, this task and production release remain blocked.

**Commit:** `feat: add approved production key wrapping`

---

## Phase D — Atomic package workflow and recovery

### Task 17: Create secure staging directories

**Files:** Create `infrastructure/filesystem.py`; tests `tests/integration/test_staging.py`.

**RED slices:** unpredictable staging name; directory permissions validated; stale partial package distinguishable; source file is never modified; symlink/reparse-point escape rejected where applicable.

**GREEN:** Stage under the same final SMB volume when atomic directory rename is required; optionally use a local encryption scratch area only if the final copy protocol safely verifies before readiness.

**Commit:** `feat: create controlled package staging`

### Task 18: Orchestrate package creation through `Verified`

**Files:** Create `application/package_service.py`; tests `tests/integration/test_package_creation.py`.

**RED vertical slices:** validate case/files → allocate unique IDs → create `Draft` → generate/wrap key → transition `Encrypting` → encrypt each file → verify encrypted hashes/container → write manifest → transition `Verified`.

**Failure tests:** unreadable source, disk full injection, duplicate ID retry, encryption exception, database busy. Failure produces `Failed`, safe audit data, and no apparently complete package.

**Commit:** one commit per state transition slice.

### Task 19: Finalize atomically and mark `Ready`

**Files:** Extend `package_service.py`; tests `tests/integration/test_finalization.py`.

**RED slices:** `Verified → Finalizing`; final directory rename; re-open and verify manifest/files from final location; only then `Finalizing → Ready`; existing destination collision fails safely; no overwrite.

**Crash windows:** Test termination after DB says `Finalizing` but before move, and after move but before `Ready` update.

**Commit:** `feat: finalize verified packages safely`

### Task 20: Reconcile interrupted operations on startup

**Files:** Create `application/reconciliation_service.py`; tests `tests/integration/test_reconciliation.py`.

**RED slices:** final files present + DB `Finalizing` → verify and mark `Ready`; only staging present → resume or mark `Failed` without guessing; neither present → mark failed and alert; unexpected final folder never auto-imported.

**GREEN:** Idempotent reconciliation and operator-readable report; no silent deletion.

**Commit:** `feat: reconcile interrupted package operations`

### Task 21: Record export metadata without cloud integration

**Files:** Extend `package_service.py`; tests `tests/integration/test_export_tracking.py`.

**RED slices:** only `Ready` can become `Exported`; destination and external reference stored separately; export-safe folder contains no PHI; repeated operation is idempotent or explicitly rejected.

**Commit:** `feat: track manual package exports`

---

## Phase E — Search, audit, backup, and recovery

### Task 22: Implement minimal search service

**Files:** Create `application/search_service.py`; tests `tests/integration/test_search.py`.

**RED slices:** exact package ID, normalized patient ID, specimen ID, destination reference; parameterized input blocks SQL injection; default result excludes wrapped keys and sensitive technical blobs.

**Commit:** `feat: search registry identifiers`

### Task 23: Implement safe audit events

**Files:** Create `infrastructure/audit.py`; tests `tests/security/test_audit_privacy.py`.

**RED slices:** creation, lookup, encrypt, verify, export, decrypt, backup, failure; signed-in Windows username and UTC timestamp recorded; raw keys, file contents, full source paths, and unnecessary patient details rejected/redacted.

**GREEN:** Structured event fields rather than arbitrary formatted logs. Define whether lookup auditing is enabled per governance decision.

**Commit:** `feat: record privacy-safe audit events`

### Task 24: Add consistent online backup

**Files:** Create `application/backup_service.py`, `scripts/backup_registry.py`; tests `tests/integration/test_backup.py`.

**RED slices:** use SQLite backup API rather than copying live DB bytes; backup has `integrity_check='ok'`; backup destination is timestamped and collision-safe; retention never removes the only known-good backup; audit success/failure.

**Commit:** `feat: create verified registry backups`

### Task 25: Add guarded restore and disaster-recovery drill

**Files:** Create `scripts/restore_registry.py`, `tests/integration/test_restore.py`, `docs/disaster-recovery.md`.

**RED slices:** reject corrupt backup; preserve current DB before restore; require registry maintenance/exclusive mode; restored package mappings and wrapped keys match expected records; package decryption test succeeds using approved recovery identity.

**Release gate:** Perform a documented restore on a replacement test workstation and reconcile package directories.

**Commit:** `feat: add verified registry restore workflow`

---

## Phase F — PyQt6 user interface

### Task 26: Start the application with a configuration health screen

**Files:** Create `ui/app.py`, `ui/main_window.py`, `__main__.py`; tests `tests/ui/test_startup.py`.

**RED slices:** valid root opens dashboard; invalid/unreachable root shows clear read-only error; migration/reconciliation runs before write actions become enabled; UI never freezes during network health checks.

**GREEN:** Use worker threads for filesystem/crypto work; all widgets remain on GUI thread.

**Commit:** `feat: add registry startup health checks`

### Task 27: Create case and package wizard

**Files:** Create `ui/create_package_page.py`; tests `tests/ui/test_create_package_page.py`.

**RED vertical slices:** required identifiers; file picker; destination selection; confirmation summary; start operation; progress/cancel semantics; success displays package ID, not key material.

**Security UX:** clearly label patient data as internal-only; warn on attempted PHI in free-text destination reference; avoid unrestricted notes in MVP.

**Commit:** one focused UI behavior per commit.

### Task 28: Add non-blocking encryption progress

**Files:** Extend UI/application worker; tests `tests/ui/test_encryption_progress.py`.

**RED slices:** progress events; app remains responsive; cancellation leaves package non-ready and cleans temporary ciphertext; close-window during work requires confirmation; exceptions produce actionable safe error.

**Commit:** `feat: show safe encryption progress`

### Task 29: Add search and package detail page

**Files:** Create `ui/search_page.py`, `ui/models.py`; tests `tests/ui/test_search_page.py`.

**RED slices:** searchable identifiers; result selection; status/files/destination/audit summary; no wrapped key blob or raw nonce/tag display; role/policy-gated decrypt action placeholder.

**Commit:** `feat: add registry search interface`

### Task 30: Add dashboard and recovery warnings

**Files:** Create `ui/dashboard_page.py`; tests `tests/ui/test_dashboard.py`.

**RED slices:** counts by state; visible stale `Encrypting/Finalizing/Failed` work; last successful backup; DB/share health; warnings do not expose patient identifiers.

**Commit:** `feat: add operational dashboard`

### Task 31: Accessibility and destructive-action review

**Files:** UI tests and styles as needed; `docs/accessibility-checklist.md`.

**Tests/checks:** keyboard navigation, labels, focus order, readable contrast, scalable text, no color-only status, confirmation for destructive/recovery actions, clear Norwegian/English terminology decision.

**Commit:** `fix: improve safe accessible workflows`

---

## Phase G — Qualification, packaging, and release

### Task 32: Add end-to-end privacy and cryptography test

**Files:** Create `tests/security/test_end_to_end_package.py`.

**RED scenario:** create case → encrypt multi-file package → finalize → search mapping → export → restore DB backup on second test environment → unwrap/decrypt → compare SHA-256. Scan DB exports, package filenames, manifest, logs, and ciphertext headers for prohibited PHI and plaintext key bytes.

**Commit:** `test: verify end-to-end secure package lifecycle`

### Task 33: Test large files and resource limits

**Files:** Create `tests/integration/test_large_file_streaming.py`, `docs/performance-baseline.md`.

**Tests:** sparse/generated large file; bounded memory; network interruption; insufficient disk space; antivirus-style temporary access denial; cancellation; throughput baseline on actual SMB share. Do not commit large fixtures.

**Commit:** `test: qualify large file streaming`

### Task 34: Harden input and failure paths

**Files:** Security tests as appropriate.

**Tests:** malicious manifest lengths, path traversal, reserved Windows names, long paths, duplicate filenames, Unicode normalization, reparse points, corrupted database, database busy timeout, clock/timezone handling, source file changed during encryption.

**Commit:** `test: harden hostile and failure inputs`

### Task 35: Build reproducible Windows package

**Files:** Create `packaging/secure-package-registry.spec`, update `pyproject.toml`, `README.md`.

**RED/validation:** clean test VM build; app starts without developer Python; dependencies/licenses inventoried; no development/test key wrapper; no test credentials/private keys; executable hash recorded; antivirus/application-control review.

**Commands:**
```bash
uv run pytest -q
uv run ruff check .
uv run mypy src
uv run pyinstaller --clean packaging/secure-package-registry.spec
```

**Commit:** `build: package windows desktop application`

### Task 36: Pilot release checklist

**Files:** Create `docs/release-checklist.md`, `docs/operator-guide.md`, `docs/admin-guide.md`.

**Release blockers:**
- Full automated suite green.
- Real SMB concurrency/disconnect qualification passed.
- Database backup and bare-workstation restore demonstrated.
- Production key recovery by a second authorized user demonstrated.
- Tamper/truncation tests passed.
- No PHI/raw keys in exported package, logs, manifests, filenames, or crash data.
- Least-privilege share/NTFS permissions reviewed.
- IT/security/privacy/clinical governance approvals recorded.
- Operator training and rollback procedure completed.

**Commit:** `docs: add pilot release and operations guides`

---

## 6. Initial schema direction

Use migrations rather than embedding a one-off `CREATE TABLE` script. The model should contain:

- `cases`: internal patient ID, specimen ID, analysis type, created metadata.
- `packages`: public package ID, case FK, workflow state, format/key versions, destination FK/reference, timestamps.
- `encryption_keys`: package FK, public key ID, wrapped blob, wrapping method/reference/version, lifecycle state.
- `package_files`: package FK, safe export name, internal source reference only if policy permits, sizes, hashes, encrypted format metadata.
- `destinations`: destination-neutral name/type and non-secret configuration.
- `audit_events`: actor, UTC timestamp, action, result, package/case references, structured safe details.

Do not place the GCM nonce/tag in several competing representations. The encrypted container is authoritative; the database may store parsed verification metadata only when it has a clear operational need.

---

## 7. Test matrix

| Area | Minimum proof |
|---|---|
| IDs | Format, randomness strategy, DB uniqueness, no PHI derivation |
| SQLite | Migrations, constraints, rollback, retries, integrity, concurrent processes |
| SMB | Real share, disconnect/termination, latency, permission denial |
| Encryption | Known answer where applicable, round trip, multi-chunk, empty/large file |
| Integrity | Header/ciphertext/tag/manifest tamper and truncation fail closed |
| Nonce safety | Unique per file under each package key; duplicate rejected |
| Privacy | No PHI/raw key in export, manifest, logs, UI technical details |
| Filesystem | Atomic staging/finalization, no overwrite, crash reconciliation |
| Key recovery | Different authorized user/workstation and replacement-machine restore |
| Backup | Online consistent backup, integrity check, full restore/decrypt drill |
| UI | Responsive workers, cancellation, keyboard/focus/accessibility, safe errors |
| Packaging | Clean Windows VM, no Python required, no test secrets/providers |

---

## 8. Open decisions to resolve before production cryptography/UI freeze

1. Exact UNC path and whether all clients access the same SMB server/namespace.
2. Approximate users, simultaneous writers, package frequency, and maximum file/package sizes.
3. Exact patient/case fields required; default proposal is patient ID + specimen ID + analysis type only.
4. Allowed source file types and whether folders are flattened, recursively preserved, or rejected.
5. Which users may create, search, decrypt, export, back up, and restore.
6. Approved production key-wrapping and disaster-recovery mechanism.
7. Whether lookup/view events must be audited.
8. Required retention/deletion rules for mappings, encrypted packages, staging data, backups, and audit events.
9. Norwegian, English, or bilingual UI.
10. Whether BaseSpace receives already-encrypted objects and how recipients obtain authorized decryption capability; confirm the actual operational workflow before calling the export BaseSpace-compatible.

---

## 9. Recommended first implementation milestone

Stop after Tasks 1–10 for Milestone 1: a tested, non-PHI registry prototype that validates SQLite behavior on the real shared drive. Do **not** process patient data or build production encryption until the SMB qualification and key-recovery design have passed review. Then implement Tasks 11–25 as the secure package engine before building most of the UI.

This order deliberately tests the two highest-risk architectural assumptions—shared SQLite and shared recoverable key custody—before investing heavily in screens or vendor integration.
