# MolKey ↔ eMolPat Portal Integration Handoff

> **Purpose:** This document is written to be pasted into the eMolPat coding chat.
> It contains everything that chat needs to add MolKey as a portal module without
> needing access to this repository's history.

---

## 1. What MolKey is

**MolKey** is a standalone PyQt6 desktop app for molecular pathology that manages
*permanent patient pseudonyms* ("MolKeys", format `MK-YYYY-XXXXXXXX`). It keeps the
internal patient-ID ↔ key mapping exclusively inside a shared SQLite registry on an
approved secure network drive, and exports **keys only** (CSV/JSON, no patient IDs)
for use in upload systems.

- Repository: `https://github.com/Christian-Bjornstad/MolKey`
  *(renamed from `MolVault`; GitHub redirects the old URL automatically)*
- Current version: **0.2.0**, package name `molkey`, console script `molkey`.
- Entry point suitable for the portal: **`molkey.__main__:main`** — returns the
  Qt exit code as `int`, exactly like the other suite modules.
- Stack: Python ≥3.11,<3.15 · PyQt6 · platformdirs · portalocker · SQLite.
  No server, no cloud, no cryptography dependency.
- Quality state at handoff: 107 tests green, Ruff clean, mypy strict clean.

## 2. What MolKey needs from the host machine

| Requirement | Detail |
|---|---|
| Secure shared folder | e.g. `K:\Sensitivt\...\Utvikling` — validated at startup (UNC or *active* mapped drive only) |
| Environment override | `MOLKEY_REGISTRY_ROOT` — if set, MolKey uses it and skips QSettings lookup. The portal launcher can set this per workstation. |
| Database bootstrap | Automatic: folders + `registry.db` + migrations are created on first start. No manual setup. |
| Write coordination | SQLite rollback journal (`DELETE`), `synchronous=FULL`, `busy_timeout=5000`, short `BEGIN IMMEDIATE` transactions plus a `portalocker` writer lock — safe for multiple simultaneous users on SMB. |

## 3. Exact changes required in eMolPat

### 3.1 `src/emolpat/ui/resources/suite-manifest.json`

Append to `modules` (schema_version 1 is unchanged):

```json
{
  "id": "molkey",
  "name": "MolKey",
  "distribution": "molkey",
  "version": "0.2.0",
  "import_name": "molkey",
  "entry_point": "molkey.__main__:main",
  "icon": "icons/molkey.png",
  "description_nb": "Permanent pseudonymer for pasienter i molekylær patologi.",
  "description_en": "Permanent patient pseudonym keys for molecular pathology.",
  "unit": "molpat"
}
```

**Decision needed:** `unit`. Existing values are `hemato` and `stat`. MolKey is
cross-cutting (used before sequencing, not tied to one unit). Suggested new value
`"molpat"`; alternatively `"felles"` — whatever convention the portal prefers for
cross-unit tools.

### 3.2 `release/components.json`

Add a pinned component (pin the commit you actually release from):

```json
{
  "id": "molkey",
  "repository": "https://github.com/Christian-Bjornstad/MolKey.git",
  "commit": "<PIN AT RELEASE TIME>",
  "distribution": "molkey",
  "import_name": "molkey",
  "entry_point": "molkey.__main__:main",
  "test_command": ["python", "-m", "pytest", "-q"]
}
```

### 3.3 Icon asset

Add `src/emolpat/ui/resources/molkey.png` (the other modules use PNG;
LVMS uses SVG). The finalized brand mark is the **Designer master** (navy
squircle tile: key + database + molecular network) with transparent
rounded corners; the source of truth is
`assets/molkey_icon_designer.png`, and the render pipeline
`scripts/render_icons.py` regenerates the full PNG set (512/256/64/32/16,
transparent corners) plus the multi-resolution `molkey_icon.ico`. Copy the
256 px PNG for the portal card.

### 3.4 Release requirements

Add to `release/requirements.in` / `.lock` (offline FELLES wheel set):

```
PyQt6>=6.7,<7
platformdirs>=4.3,<5
portalocker>=3,<4
```

All three already ship in the suite's offline environment or are pure-python/
widely wheeled; verify the FELLES wheel mirror holds `PyQt6` for **Python 3.14**
(the suite pins `python_requires = ">=3.14,<3.15"`; MolKey itself allows ≥3.11,
so 3.14 is compatible).

## 4. How launch works (no portal code changes expected)

The standard flow already fits MolKey with zero portal-side logic changes:

1. User clicks the MolKey card → portal spawns
   `python -m emolpat.module_runner molkey`.
2. `module_runner.run_module` resolves `bundled_manifest().module("molkey")`,
   resolves entry point `molkey.__main__:main`, calls it.
3. MolKey initializes/migrates the shared registry automatically and shows the
   window. The portal stays open (existing stay-open behavior).

If the portal wants to force the registry location, set `MOLKEY_REGISTRY_ROOT`
in the child environment before spawn — MolKey honors it above QSettings.

## 5. Validation checklist for the eMolPat chat

- [ ] `python -m pytest -q` passes inside the checked-out MolKey component.
- [ ] `scripts/validate_manifest_consistency.py` accepts the new module
      (manifest ↔ components agreement: id, distribution, import_name, entry point).
- [ ] `python -m emolpat.module_runner molkey` starts the UI from the built suite.
- [ ] Offline suite smoke (`scripts/smoke_installed_suite.py`) still green.
- [ ] First run on a clean workstation creates folders + `registry.db` under the
      configured root without user interaction.
- [ ] Two simultaneous instances on different workstations can generate keys
      without lock errors (writer-lock coordination).

## 6. Known constraints / good to know

- MolKey validates its root path: plain local paths (e.g. `C:\...`) are rejected;
  UNC paths and Windows-confirmed active mapped drives are accepted. Point the
  setting or `MOLKEY_REGISTRY_ROOT` at the approved secure share.
- Exports contain generated keys only — patient IDs never leave the database.
  This is intentional and safety-relevant; do not "improve" exports to include IDs.
- Schema is at v2 (`patient_keys` table added in v2). Upgrades are automatic and
  additive; older v1 databases migrate on first connect.
