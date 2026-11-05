# V3.3 — Safe local artifact retention and cleanup

V3.3 completes the **owner-reviewed, reversible retention workflow**. It does
not add a destructive automatic cleaner or silently delete business records.

## Scope

- A bounded inventory for applied local websites and generated media runs.
- Exact tree SHA-256 and per-file digests for an explicitly selected artifact.
- A local ZIP snapshot in \`data/backups/agentforge/<backup-id>.zip\` with a
  separate receipt/manifest. The source is rechecked after the ZIP is built.
- Verification of archive SHA, file list, file sizes and each file SHA.
- Explicit, SHA-bound **quarantine**, available only with **Operations PAUSED**,
  for an artifact with a successfully verified local backup.
- Explicit, SHA-bound non-overwriting **restore** from quarantine.
- No permanent-delete endpoint, no automatic cleanup, no delete-on-success.
  Quarantine moves a folder out of the active products/media namespace; **it
  does not free disk space**. A future irreversible purge would need a separate
  policy, long retention period and owner-review workflow.

**Never targeted:** \`data/company/*.sqlite3\`, task history, owner approvals,
customer contacts, configuration, model weights, and proposal review history.

## Command-line recovery/acceptance

From Windows PowerShell:

    cd D:\AgentForge
    .\.venv\Scripts\python.exe -m agentforge.storage.retention inventory

Choose a website slug or media run ID, then inspect its exact tree hash:

    .\.venv\Scripts\python.exe -m agentforge.storage.retention inspect website YOUR-SLUG

Create a snapshot, using exactly that digest:

    .\.venv\Scripts\python.exe -m agentforge.storage.retention backup website YOUR-SLUG --tree-sha SHA --confirm

Verify backup via the returned backup ID:

    .\.venv\Scripts\python.exe -m agentforge.storage.retention verify BACKUP_ID

To move active output into reversible quarantine, first use Operations →
**Pause Operations** in the authenticated Dashboard. Then:

    .\.venv\Scripts\python.exe -m agentforge.storage.retention quarantine BACKUP_ID --tree-sha SHA --confirm

Restore when needed, while Operations is still PAUSED:

    .\.venv\Scripts\python.exe -m agentforge.storage.retention restore BACKUP_ID --tree-sha SHA --confirm

Do not resume Operations until the product/media state is inspected.

## Existing full-business backup remains independent

\`agentforge.ops_backup\` continues to provide **consistent SQLite snapshots**
through \`sqlite3.Connection.backup()\`, optional workspace inclusion,
verification and **staged** non-overwriting recovery. V3.3's retention ZIP is
per-artifact and is **not a substitute for a full \`data/\` disaster backup**.
Use the existing ops backup runbook for complete company recovery.

## Safety and limitations

- Only \`workspace/products/SLUG\` or \`workspace/media/RUN_ID\` can be selected;
  no freeform filesystem path or arbitrary recursive delete is supported.
- Symlinks and Windows junctions are refused at every traversed level.
- Backups are bounded to 250 files / 350 MiB total / 160 MiB per file. Bigger
  sites/videos require the existing full-backup pipeline rather than bypassing
  limits.
- Backup and quarantine are **owner-local only**; no upload, cloud sync or
  remote storage.
- If interrupted between a directory move and receipt update, the system does
  not automatically retry or delete anything. Inspect the archive, receipt and
  quarantine directory manually before proceeding.
- Backups may contain private commercial content and are not encrypted by this
  utility. Rely on OS encryption/access controls and do not commit or share them.
- ZIP digest verification detects accidental corruption but does not provide
  cryptographic authentication against an attacker who can modify both the
  ZIP and its local manifest.

Source: \`src/agentforge/storage/retention.py\`; tests:
\`tests/test_retention_v33.py\`.

## End of V3.3 implementation scope

After V3.3 merges and Windows CI passes, **stop feature development**. The owner
will verify the local Windows build, upload a real website/media sample, check
review/permission controls, and decide the next roadmap from actual evidence.

## React owner flow

In the new Dashboard at `/dashboard/`, choose **Backups & Cleanup**:
**Inspect SHA → Create ZIP backup → Verify ZIP & SHA → Pause Operations →
Quarantine / Restore**. Each write requires a deliberate owner confirmation,
and the Python backend verifies state/SHA again. The legacy CLI remains
available for recovery.

