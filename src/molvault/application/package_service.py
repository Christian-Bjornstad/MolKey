"""Application service for creating package drafts."""

from __future__ import annotations

import hashlib
import json
import secrets
import shutil
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from molvault.domain.identifiers import generate_package_id
from molvault.domain.models import CaseRecord, PackageRecord
from molvault.domain.states import PackageState
from molvault.infrastructure.database import connect
from molvault.infrastructure.repositories import (
    CaseRepository,
    EncryptionKeyRecord,
    EncryptionKeyRepository,
    PackageFileRecord,
    PackageFileRepository,
    PackageRepository,
)
from molvault.security.key_protection import protect_key


@dataclass(frozen=True)
class StagedSourceFile:
    """A source selected for a draft, with a PHI-free export name."""

    source_path: Path
    export_name: str


@dataclass(frozen=True)
class PreparedPackage:
    """Verified package artifacts held internally until manual export."""

    package_id: str
    workspace: Path
    manifest_path: Path


class PackageService:
    """Coordinate case mapping and pseudonymous package creation."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.cases = CaseRepository(db_path)
        self.packages = PackageRepository(db_path)
        self.keys = EncryptionKeyRepository(db_path)
        self.package_files = PackageFileRepository(db_path)
        self._source_files: dict[str, list[StagedSourceFile]] = {}
        self._prepared: dict[str, PreparedPackage] = {}

    def create_draft(
        self,
        *,
        patient_id: str,
        case_number: str,
        destination: str | None = None,
        notes: str = "",
    ) -> PackageRecord:
        patient_value = patient_id.strip()
        case_value = case_number.strip()
        if not patient_value:
            raise ValueError("Patient ID is required")
        if not case_value:
            raise ValueError("Case number is required")

        internal_patient_id = _with_prefix(patient_value, "PAT-")
        case = self._find_case(internal_patient_id, case_value)
        if case is None:
            case = CaseRecord(
                case_id=f"CASE-{secrets.token_hex(6).upper()}",
                patient_id=internal_patient_id,
                specimen_id=_with_prefix(case_value, "SPEC-"),
            )
            self.cases.add(case)

        package = PackageRecord(
            package_id=generate_package_id(),
            case_id=case.case_id,
            key_id="KEY-PENDING",
            destination=destination.strip() if destination and destination.strip() else None,
            notes=notes.strip(),
        )
        self.packages.add(package)
        return package

    def add_source_files(
        self, package_id: str, source_paths: list[Path]
    ) -> list[StagedSourceFile]:
        package = self.packages.get(package_id)
        if package is None:
            raise ValueError(f"Package not found: {package_id}")
        staged = self._source_files.setdefault(package_id, [])
        for source_path in source_paths:
            path = Path(source_path)
            if not path.is_file():
                raise ValueError(f"Source file does not exist: {path}")
            sequence = len(staged) + 1
            suffix = path.suffix.lower()
            staged.append(
                StagedSourceFile(
                    source_path=path,
                    export_name=f"{package_id}-{sequence:03d}{suffix}",
                )
            )
        return list(staged)

    def list_source_files(self, package_id: str) -> list[StagedSourceFile]:
        return list(self._source_files.get(package_id, []))

    def encrypt_and_verify(self, package_id: str) -> PreparedPackage:
        """Encrypt staged files, authenticate them, verify, and mark Ready."""
        package = self.packages.get(package_id)
        if package is None:
            raise ValueError(f"Package not found: {package_id}")
        staged = self.list_source_files(package_id)
        if not staged:
            raise ValueError("Package must contain at least one file")

        workspace = self.db_path.parent / ".molkey-packages" / package_id
        if workspace.exists():
            shutil.rmtree(workspace)
        workspace.mkdir(parents=True)
        key = AESGCM.generate_key(bit_length=256)
        cipher = AESGCM(key)
        key_id = f"KEY-{secrets.token_hex(8).upper()}"
        manifest_files: list[dict[str, object]] = []

        self.packages.transition(package_id, PackageState.ENCRYPTING)
        for item in staged:
            plaintext = item.source_path.read_bytes()
            nonce = secrets.token_bytes(12)
            associated_data = f"{package_id}:{item.export_name}".encode()
            ciphertext = cipher.encrypt(nonce, plaintext, associated_data)
            encrypted_name = f"{item.export_name}.enc"
            encrypted_path = workspace / encrypted_name
            encrypted_path.write_bytes(ciphertext)
            checksum = hashlib.sha256(ciphertext).hexdigest()
            if cipher.decrypt(nonce, ciphertext, associated_data) != plaintext:
                raise ValueError(f"Verification failed for {item.export_name}")
            self.package_files.add(
                PackageFileRecord(
                    package_id=package_id,
                    export_name=encrypted_name,
                    original_size=len(plaintext),
                    encrypted_size=len(ciphertext),
                    nonce=nonce,
                    checksum=checksum,
                )
            )
            manifest_files.append(
                {
                    "name": encrypted_name,
                    "size": len(ciphertext),
                    "sha256": checksum,
                    "nonce": nonce.hex(),
                }
            )

        wrapped_key = protect_key(key, entropy=package_id.encode())
        self.keys.add(
            EncryptionKeyRecord(key_id, package_id, wrapped_key, "AES-256-GCM", 1)
        )
        manifest_path = workspace / "manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "format": "MolKey secure package",
                    "version": 1,
                    "package_id": package_id,
                    "algorithm": "AES-256-GCM",
                    "key_id": key_id,
                    "files": manifest_files,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        self.packages.transition(package_id, PackageState.VERIFIED)
        self.packages.transition(package_id, PackageState.FINALIZING)
        self.packages.transition(package_id, PackageState.READY)
        result = PreparedPackage(package_id, workspace, manifest_path)
        self._prepared[package_id] = result
        return result

    def export_package(self, package_id: str, destination: Path) -> Path:
        """Copy a verified package to a user-selected folder."""
        package = self.packages.get(package_id)
        if package is None:
            raise ValueError(f"Package not found: {package_id}")
        if package.state is not PackageState.READY:
            raise ValueError("Only Ready packages can be exported")
        prepared = self._prepared.get(package_id)
        if prepared is None:
            workspace = self.db_path.parent / ".molkey-packages" / package_id
            prepared = PreparedPackage(package_id, workspace, workspace / "manifest.json")
        if not prepared.workspace.is_dir() or not prepared.manifest_path.is_file():
            raise ValueError("Verified package artifacts are unavailable")
        destination_root = Path(destination)
        destination_root.mkdir(parents=True, exist_ok=True)
        export_path = destination_root / package_id
        if export_path.exists():
            raise ValueError(f"Export destination already exists: {export_path}")
        shutil.copytree(prepared.workspace, export_path)
        for source in prepared.workspace.iterdir():
            copied = export_path / source.name
            if not copied.is_file() or hashlib.sha256(copied.read_bytes()).digest() != hashlib.sha256(
                source.read_bytes()
            ).digest():
                shutil.rmtree(export_path, ignore_errors=True)
                raise ValueError(f"Export verification failed for {source.name}")
        self.packages.transition(package_id, PackageState.EXPORTED)
        return export_path

    def _find_case(self, patient_id: str, case_number: str) -> CaseRecord | None:
        conn = connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT id FROM cases WHERE patient_id = ? AND case_number = ?",
                (patient_id, case_number),
            ).fetchone()
        finally:
            conn.close()
        return self.cases.get(str(row["id"])) if row is not None else None


def _with_prefix(value: str, prefix: str) -> str:
    return value if value.startswith(prefix) else f"{prefix}{value}"
