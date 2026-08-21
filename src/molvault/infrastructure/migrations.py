"""Schema migrations for MolVault registry."""

import sqlite3
from pathlib import Path

from molvault.infrastructure.writer_lock import get_registry_root_from_db, writer_lock

SCHEMA_VERSION = 1

MIGRATION_001 = """
-- Schema version table
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Cases: internal hospital case records
CREATE TABLE IF NOT EXISTS cases (
    id TEXT PRIMARY KEY,                    -- CASE-XXXXXXXX
    patient_id TEXT NOT NULL,               -- Internal patient identifier
    case_number TEXT NOT NULL,              -- DIT format: YYORGNNNNN (e.g., 26OUM12287)
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(patient_id, case_number)
);

-- Packages: pseudonymous transfer units
CREATE TABLE IF NOT EXISTS packages (
    id TEXT PRIMARY KEY,                    -- SPK-YYYY-XXXXXXXXXXXX (12 hex chars)
    case_id TEXT NOT NULL,                  -- FK to cases.id
    state TEXT NOT NULL CHECK (state IN (
        'Draft', 'Encrypting', 'Verified', 'Finalizing', 'Ready', 'Exported', 'Archived', 'Failed'
    )),
    destination TEXT,                       -- BaseSpace, ExternalLab, Research, Archive
    destination_ref TEXT,                   -- External tracking ID
    checksum TEXT,                          -- SHA-256 of manifest
    size_bytes INTEGER,                     -- Total encrypted size
    key_id TEXT,                            -- FK to encryption_keys.id
    notes TEXT,                             -- Internal notes only
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE RESTRICT,
    FOREIGN KEY (key_id) REFERENCES encryption_keys(id) ON DELETE SET NULL
);

-- Encryption keys: wrapped DEKs per package
CREATE TABLE IF NOT EXISTS encryption_keys (
    id TEXT PRIMARY KEY,                    -- KEY-XXXXXXXX
    package_id TEXT NOT NULL,               -- FK to packages.id
    wrapped_key BLOB NOT NULL,              -- DPAPI/certificate-wrapped DEK
    algorithm TEXT NOT NULL DEFAULT 'AES-256-GCM',
    version INTEGER NOT NULL DEFAULT 1,     -- Key wrapping format version
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (package_id) REFERENCES packages(id) ON DELETE CASCADE
);

-- Package files: encrypted file metadata
CREATE TABLE IF NOT EXISTS package_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    package_id TEXT NOT NULL,               -- FK to packages.id
    export_name TEXT NOT NULL,              -- Safe export filename (no PHI)
    original_size INTEGER NOT NULL CHECK (original_size >= 0),  -- Original file size
    encrypted_size INTEGER NOT NULL CHECK (encrypted_size >= 0), -- Encrypted file size
    nonce BLOB NOT NULL CHECK (length(nonce) = 12),             -- 96-bit GCM nonce
    checksum TEXT NOT NULL CHECK (length(checksum) = 64 AND checksum NOT GLOB '*[^0-9a-f]*'), -- SHA-256 hex
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (package_id) REFERENCES packages(id) ON DELETE CASCADE
);

-- Prevent path traversal and absolute paths in export_name
CREATE TRIGGER IF NOT EXISTS trg_package_files_export_name_safe
BEFORE INSERT ON package_files
FOR EACH ROW
WHEN NEW.export_name GLOB '*[/\\]*'
   OR NEW.export_name GLOB '*..*'
   OR NEW.export_name GLOB '/*'
   OR NEW.export_name GLOB '\\*'
   OR NEW.export_name = ''
   OR LENGTH(NEW.export_name) > 255
BEGIN
    SELECT RAISE(ABORT, 'export_name must be a safe basename without path separators, .., or leading slash/backslash');
END;

-- Destinations: configured export targets
CREATE TABLE IF NOT EXISTS destinations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,              -- BaseSpace, ExternalLab, Research, Archive
    type TEXT NOT NULL,                     -- s3, sftp, filesystem, basespace
    config_json TEXT NOT NULL,              -- JSON configuration (no secrets)
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Audit events: security-relevant actions
CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    package_id TEXT,                        -- Optional FK to packages.id
    case_id TEXT,                           -- Optional FK to cases.id
    action TEXT NOT NULL,                   -- create, encrypt, verify, finalize, export, decrypt, backup, restore, fail
    operator TEXT NOT NULL,                 -- Windows username
    result TEXT NOT NULL CHECK (result IN ('success', 'failure')),
    details TEXT,                           -- JSON safe details (no keys, no PHI)
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (package_id) REFERENCES packages(id) ON DELETE SET NULL,
    FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE SET NULL
);

-- Indexes for search performance
CREATE INDEX IF NOT EXISTS idx_packages_case_id ON packages(case_id);
CREATE INDEX IF NOT EXISTS idx_packages_state ON packages(state);
CREATE INDEX IF NOT EXISTS idx_packages_destination_ref ON packages(destination_ref);
CREATE INDEX IF NOT EXISTS idx_cases_patient_id ON cases(patient_id);
CREATE INDEX IF NOT EXISTS idx_cases_case_number ON cases(case_number);
CREATE INDEX IF NOT EXISTS idx_encryption_keys_package_id ON encryption_keys(package_id);
CREATE INDEX IF NOT EXISTS idx_package_files_package_id ON package_files(package_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_package_id ON audit_events(package_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_timestamp ON audit_events(timestamp);
"""


def migrate(db_path: Path) -> None:
    """Apply schema migrations to the database.

    Idempotent: safe to call multiple times.
    Acquires the registry writer lock to serialize with other writers.
    Executes DDL and version upsert in a single explicit transaction.
    """
    registry_root = get_registry_root_from_db(db_path)

    with writer_lock(registry_root, timeout=30.0):
        conn = sqlite3.connect(db_path)
        try:
            # Enable foreign keys for this connection
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = DELETE")
            conn.execute("PRAGMA synchronous = FULL")
            conn.execute("PRAGMA busy_timeout = 5000")
            conn.execute("PRAGMA temp_store = MEMORY")

            # Check current schema version in an explicit transaction
            conn.execute("BEGIN IMMEDIATE")
            try:
                cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'")
                if cursor.fetchone() is None:
                    # Fresh database - apply migration 001
                    conn.executescript(MIGRATION_001)
                    conn.execute(
                        "INSERT INTO schema_version (version) VALUES (?)",
                        (SCHEMA_VERSION,),
                    )
                else:
                    # Check version
                    cursor = conn.execute("SELECT version FROM schema_version")
                    row = cursor.fetchone()
                    current_version = row[0] if row else 0

                    if current_version > SCHEMA_VERSION:
                        raise RuntimeError(
                            "Database schema version "
                            f"{current_version} is newer than supported version {SCHEMA_VERSION}. "
                            "Upgrade MolVault to access this database."
                        )

                    if current_version < SCHEMA_VERSION:
                        # Apply pending migrations
                        conn.executescript(MIGRATION_001)
                        conn.execute(
                            "UPDATE schema_version SET version = ?, applied_at = datetime('now')",
                            (SCHEMA_VERSION,),
                        )
                    # If current_version == SCHEMA_VERSION, nothing to do

                conn.commit()
            except Exception:
                conn.rollback()
                raise
        finally:
            conn.close()


def get_schema_version(db_path: Path) -> int:
    """Get current schema version of the database."""
    if not db_path.exists():
        return 0
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'")
        if cursor.fetchone() is None:
            return 0
        cursor = conn.execute("SELECT version FROM schema_version")
        row = cursor.fetchone()
        return row[0] if row else 0
    finally:
        conn.close()