# MolVault

**Secure Package Registry for molecular pathology**

MolVault is a planned PyQt6 desktop application for creating pseudonymous package IDs, encrypting data packages with AES-256-GCM, and maintaining the protected relationship between packages and hospital case identifiers.

## Project status

Planning and test-driven development setup. The implementation plan is available at:

- [TDD implementation plan](.hermes/plans/2026-08-20_secure-package-registry-tdd-plan.md)

## Planned architecture

- PyQt6 desktop interface
- SQLite registry on an access-controlled hospital shared drive
- AES-256-GCM authenticated encryption
- Recoverable, wrapped per-package encryption keys
- Destination-neutral manual export workflow
- Strict RED → GREEN → REFACTOR development

> MolVault is not approved for real patient data until hospital IT, security, privacy, key recovery, SMB concurrency, backup, and disaster-recovery requirements have been validated.
