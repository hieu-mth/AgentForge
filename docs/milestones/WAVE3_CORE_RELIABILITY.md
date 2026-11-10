# AgentForge — Wave 3 Core Reliability (AF-AUD-003 / 004 / 009 / 017)

**Scope:** targeted fixes to crash-recovery coordination, inspection-only
SQLite access, terminal local ComfyUI errors and health status accounting.
No new model provider, automatic retries, publishing, database migration or
destructive cleanup is introduced.

## Recovery: exact changed goal IDs (003)

- `brain_store.recover()` keeps its historical integer return by default;
  `return_ids=True` gives the exact set of goals actually transitioned from
  `RUNNING` to `INTERRUPTED` in one SQLite write transaction.
- `brain_runner.recover()` uses this exact set, not a 100-item recent-goal
  projection, and interrupts the corresponding *currently RUNNING* parent and
  child S1 tasks.
- Markers `DISPATCHING`, existing task results, signed goal plans and all
  completed work remain intact. An interrupted / uncertain attempt is never
  automatically replayed. Unrelated S1 tasks are unchanged.
- A crash between S4 and S1 database updates can leave a partially
  reconciled state. Each subsequent explicit recovery also revisits S1 task
  IDs linked to **previously INTERRUPTED** S4 goals, so RUNNING entries are
  reconciled without replay or duplicate S4 events. This is still not a
  cross-database atomic transaction; any remaining discrepancy requires
  Owner inspection.

## SQLite read boundary and Owner GET (004)

- S1 task list/detail/count, S4 goal list/detail/count and Autopilot policy/
  report/quality inbox use explicit read-only SQLite connections.
- Absent databases return empty/default inspection results without
  initializing files or schemas. A legacy V1.3 Autopilot database without
  quality tables returns an empty quality inbox; V1.4 schema is still
  initialized at **explicit write** boundaries as before.
- The authenticated bootstrap and operations doctor remain inspection-only
  within their supported storage paths. Corruption is not silently migrated.

## Local film terminal failure (009)

- `job_status(job_id)` with a confirmed ComfyUI history status
  `error` / `failed` performs a guarded durable transition
  `SUBMITTED -> FAILED`.
- `FAILED` is terminal, releases the **one-active-job** quota and does not
  trigger automatic resubmission or allow the same job/shot/plan to be replayed.
- Pending/incomplete/missing history and `SUBMITTING` after an ambiguous
  request **retain** quota; an absent or malformed history is not proof of
  failure.
- A separate, distinct shot may be Owner-submitted after terminal failure;
  it still requires the original explicit consent, trusted workflow SHA and
  runtime prerequisites.
- This does not establish that ComfyUI, Wan, GPU or generated MP4 works on the
  Owner's machine.

## Global running counts (017)

- `ops_doctor.inspect()` counts matching `RUNNING` status with read-only SQL
  across the **entire** S1/S4 tables, not latest 200 tasks / 100 goals.
- An unreadable or corrupt count is a FAIL with
  `running_count_unavailable`, not a false-zero green health result.
- UI recent-items remain bounded independently.

## Regression/acceptance gates

1. `python -m unittest tests.test_wave3_core_reliability -v`
2. `python -m unittest discover -s tests -v`
3. Windows CI: Python 3.13, dashboard and NovaMart builds, Edge smoke,
   PowerShell 5.1 acceptance and source-hygiene checks.
4. Adversarial probes: >100 goals and >200 tasks hiding the original RUNNING
   entry; exact parent+child recovery, fault-injected S4/S1 crash continuation and unrelated RUNNING task preserved;
   no files/schema on missing/legacy GET; corrupted status counts fail;
   terminal error versus pending ComfyUI history and quota release.

**Not certified:** true process-crash injection, power-failure SQLite
durability, real ComfyUI failure behavior, cross-DB atomic reconciliation or
production deployment. These need an Owner-authorized runtime drill.
