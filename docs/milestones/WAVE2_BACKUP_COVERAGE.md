# Wave 2 — Coverage-aware local backup and staged restore

**Scope:** AF-AUD-002. This is a bounded disaster-recovery **inventory**, not
production disaster-recovery certification. The Wave 1 ZIP path containment
checks remain in place. No cloud upload, credentials retrieval or automatic
cutover is introduced.

## Two distinct backup modes

- Default `create --confirm-backup` remains **database-only** for CLI
  compatibility. Only `data/company/*.sqlite3` is captured. The manifest
  and command output explicitly say `PARTIAL_DATABASE_ONLY`; **do not treat
  this as a complete restore point**.
- `create --include-workspace --confirm-backup` captures known first-party
  runtime storage scopes using manifest schema 2. Exact bytes/SHA and the
  included/excluded scope inventory are recorded. Expected result is
  `KNOWN_SCOPES_COVERED` unless an unrecognized data/workspace top-level
  location is found, in which case it is `REVIEW_REQUIRED`.

Schema 1 archives remain verifiable and stage-restorable, but are labeled
`LEGACY_UNATTESTED`. Do not infer their original coverage from checksums.

## Source-traced scopes (schema 2 full mode)

| Included | Contents |
|---|---|
| `data/company/**` | SQLite snapshots and nested proposal, revision, owner-review, policy, task and ledger records |
| `data/film_studio/**` | Motion job SQLite and related receipts |
| `data/research/**` | Research reports |
| `data/checkpoints.sqlite`, `data/tool_integration.sqlite` | LangGraph/checkpoint databases |
| `data/backups/agentforge/**` | Owner-managed per-artifact retention ZIPs and receipts |
| `workspace/products/**` | Applied websites and local raster assets |
| `workspace/media/**`, `workspace/media_inputs/**` | Media outputs and explicit input assets |
| `workspace/growth/**`, `workspace/analytics/**` | Growth packages and analytics inputs |
| `workspace/webapps/**` | Applied React app sources |
| `workspace/visuals/**` | Shared SHA-bound image outputs |
| `workspace/films/**` | Reviewed shots, clip receipts and film masters |
| `workspace/webapp-browser-qa/**` | Browser QA reports and screenshots |
| `workspace/.quarantine/**` | Reversibly quarantined local artifacts |

Intentionally excluded: `workspace/backups/**` (would recursively copy the
archive being created), `workspace/.webapp-qa-staging/**` (disposable),
SQLite WAL/SHM/journal sidecars (the SQLite database is snapshotted online),
the transient `ops_daemon.lock` file, model weights, .env/credentials and
external paths. The backup has an individual 250 MiB and aggregate 1.5 GiB
budget. Large film/video backups may require a separate Owner-selected,
encrypted archive workflow; the tool fails instead of silently omitting files.

An unknown top-level location under data/workspace is reported in
`coverage.unrecognized_locations` and changes coverage to `REVIEW_REQUIRED`.
New features must be added to the inventory before claiming coverage. A
known-scope inventory can still miss external providers, manually relocated
storage or model dependencies; check these separately.

## Owner procedure (Windows PowerShell)

Stop tasks, Control Center, daemon/scheduler and other writers before taking
a coordinated full restore point. Although each SQLite file uses an online
transaction-consistent snapshot, **the set of databases and filesystem assets
is not an atomic multi-file snapshot**.

```powershell
cd D:\AgentForge
.\.venv\Scripts\python.exe -m agentforge.ops_backup create --include-workspace --confirm-backup
# Copy the returned archive path into $archive only on the local machine.
$archive = "D:\AgentForge\workspace\backups\agentforge-YYYYMMDDTHHMMSSZ-xxxxxxxx.zip"
.\.venv\Scripts\python.exe -m agentforge.ops_backup verify $archive
$target = "D:\AgentForge-restore-review-$(Get-Date -Format yyyyMMdd-HHmmss)"
.\.venv\Scripts\python.exe -m agentforge.ops_backup stage-restore $archive $target --confirm-restore
```

Review manifest contents, exclusions and warnings **before** any manual
cutover. Stage restore always creates a new absent directory, rechecks
digests, and never overwrites active databases or products.

**Reference validation limitations:** per-file checksums and SQLite
`PRAGMA integrity_check` are verified. Cross-file business references,
external credentials/providers, deployed websites, image/model availability,
completed task state and cross-database transaction consistency are **not
certified automatically**. The result flags this explicitly as
`reference_integrity_certified: false`. Validate artifact SHA links,
proposal/QA/review receipts and business records in a separate Owner test
workspace before promoting a staged restore.

Backups may include sensitive unencrypted business data and are neither
authenticated nor encrypted. Restrict filesystem access, store an additional
encrypted/offline copy and never commit or upload archives as plain files.

## Verification and backward compatibility

- `python -m unittest tests.test_ops_reliability tests.test_wave1_security tests.test_wave2_backup_coverage -v`
- `python -m unittest discover -s tests -v` + Windows CI.
- Schema 1 still works, but its coverage is `LEGACY_UNATTESTED`.
- Database-only callers retain the same included file set and
  `CREATED_AND_VERIFIED` / `PASS` operational status, with additional
  coverage warning fields.
- This change does **not** change feature runtimes, provider selection,
  task execution, generated artifact content or active state.
