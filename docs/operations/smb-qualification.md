# SQLite-on-SMB qualification gate

MolKey's shared SQLite registry is **not production-approved** until the
hospital's IT, security, and privacy teams have reviewed the deployment and the
concurrency tests pass on the intended SMB share from at least two authorized
workstations.

## Safety

- Create an isolated, empty test folder on the intended SMB share. Point both
  workstations at that folder, never at a live registry. Include `qualification`
  in its folder name. The script refuses an existing unmarked registry and
  creates a marker for its own test registry. It leaves synthetic `PATSMB*`
  patient IDs and generated MolKeys behind.
- Do not use patient data during qualification.
- Coordinate the test with hospital IT because it exercises concurrent file
  locking and network interruption.
- Keep the test folder access-controlled. Remove it after retaining the evidence
  and confirming it contains only test data.

## 1. Baseline concurrent writers

From workstation A:

```bash
uv run python scripts/qualify_smb.py "//server/secure-share/MolKey-qualification" --workers 4 --writes 25
```

Repeat from workstation B while workstation A is still running, increasing
`--writes` if necessary to overlap the runs.

Pass criteria:

- `passed` is `true`
- `integrity_check` is `ok`
- `journal_mode` is `DELETE`
- all worker exit codes are `0`
- `errors` is empty
- observed synthetic rows are at least the expected count

The script creates patient keys through MolKey's normal service in the same
`molkey-registry.db` file and refreshes the Excel register after each write.
It checks that all writes and workbook updates succeed, then checks database
integrity. The desktop workflow still needs the manual check below.

## 2. Application workflow on the same test registry

1. Set both desktop apps to the isolated test folder. Enter operator initials on
   each workstation.
2. Create a synthetic patient ID such as `PATSMB001` on workstation A. Search for
   it from B, then create the same ID on B and confirm both apps show one MolKey.
3. Check that the Excel register contains this mapping. If Excel prevents a
   refresh while it is open, confirm the app reports the stale copy. Close Excel,
   use **Refresh Excel**, and confirm the mapping appears.

Pass criteria: both apps show the same key for the patient, the database has one
mapping for that patient, and Excel can be refreshed after any file lock is
released. Repeat with several distinct synthetic IDs while both apps are active.

## 3. Forced process termination

1. Start a longer run (`--workers 8 --writes 1000`).
2. Terminate one worker process from Task Manager while writes are active.
3. Let the remaining workers finish.
4. Run the qualification script again with a small workload and check its
   `integrity_check` result.

Pass criteria:

- The terminated operation is reported as failed, not silently successful.
- The database opens from both workstations.
- `PRAGMA integrity_check` returns `ok`.
- No partially committed patient-key mapping is visible.

## 4. Network interruption

With hospital IT approval:

1. Start a long qualification run.
2. Briefly interrupt the workstation's access to the share while a writer is active.
3. Restore access.
4. Verify the app reports a bounded busy/I/O error and remains usable after reconnect.
5. Re-run the baseline qualification and integrity check.

Pass criteria:

- No indefinite hang.
- No false success message.
- Database integrity remains `ok`.
- Subsequent writes and reads succeed.

## 5. Backup and restore

1. Back up the isolated qualification registry while it is idle, using an
   approved SQLite backup procedure.
2. Restore the database to a separate approved test folder.
3. Run `PRAGMA integrity_check` against the restored database and open it with
   MolKey on a test workstation. Do not run the qualification writer script
   against a restored database without its qualification marker.
4. Compare row counts, schema version, and synthetic mappings with the source.

Pass criteria:

- Restored database integrity is `ok`.
- Schema version and row counts match.
- Existing patient-key mappings remain byte-identical.

## Evidence to retain

Record the date, UNC path, workstation names, Windows versions, SMB/server
details, script output, interruption observations, integrity results,
backup/restore results, tester names, and IT/security approval. Do not include
patient identifiers or key material.

> A passing local simulation validates the test harness only. It does not satisfy this release gate.
