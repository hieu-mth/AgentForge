# AgentForge V1.4 — Business Context + Content Quality Gate + Review Queue

V1.4 extends the existing V1.3 SQLite model draft queue. It never publishes, deploys, spends, adds new S1 permissions or bypasses owner Pause and S4 source/goal SHA review.

## Business Context

Owner defines a bounded JSON profile of business/industry plus focus_phrases and blocked_phrases. Profiles are SHA-256 digested and snapshotted on new jobs. Profile updates never silently replace an existing job snapshot. When the active business profile differs from the job's immutable snapshot, queued jobs are quarantined as BLOCKED_INPUT before reserving a model-call slot. Old incompatible recurring schedules are paused rather than sending an ambiguous brief to AI.

Use this sample for mattress consulting, saved to D:\AgentForge\business-profile.json (UTF-8):

    {
      "business": "Tư vấn nệm ngủ gia đình",
      "industry": "Nệm ngủ, nệm cao su, foam và lò xo",
      "focus_phrases": ["nệm", "nệm ngủ", "giấc ngủ"],
      "blocked_phrases": ["nem chua", "nem nướng", "nem cua", "món ăn"]
    }

After release, stop the old foreground worker with Ctrl+C. Verify clean Git status, switch to main and pull. Then, from D:\AgentForge:

    .\.venv\Scripts\python.exe -m agentforge.quality_v14 set-context --input-file .\business-profile.json --confirm-context
    .\.venv\Scripts\python.exe -m agentforge.quality_v14 inbox

New media.copy_draft briefs should explicitly mention nệm ngủ in Vietnamese with correct accents. Avoid any actual customer data or secrets in the local unencrypted database.

## Review Queue

After model S1 SUCCEEDED, a separate review is recorded as PENDING with content SHA and one of:
- PASS_HEURISTIC — draft has matching business terms, no known blocked terms; still needs human review.
- BLOCKED — conflicting business terms, missing focus or invalid draft flags.
- UNASSESSED — no business context, malformed output or website proposal requiring existing source inspection.

The check uses NFC Unicode with accent-sensitive phrase boundaries, so nem chua and nem cua cannot be treated as nệm ngủ. This is a conservative rule-based check, NOT a semantic/factual validator; it can miss misleading marketing claims.

View a report and original S1 output:

    .\.venv\Scripts\python.exe -m agentforge.quality_v14 inbox
    .\.venv\Scripts\python.exe -m agentforge.task_history show TASK_ID

Approve a PASS_HEURISTIC storyboard only after reading the original Task History content:

    .\.venv\Scripts\python.exe -m agentforge.quality_v14 decide JOB_ID APPROVE --output-sha OUTPUT_SHA --confirm-review

Or reject any draft:

    .\.venv\Scripts\python.exe -m agentforge.quality_v14 decide JOB_ID REJECT --output-sha OUTPUT_SHA --confirm-review

Replace JOB_ID, TASK_ID and OUTPUT_SHA with the exact values in the report. Approval is one-time and SHA-bound, and NEVER invokes a model, renders video, applies website files, publishes or contacts customers. Website source proposals remain UNASSESSED and require separate existing owner source inspection and SHA apply; they cannot be approved here.

If an old V1.3 recurring schedule uses the unaccented nem brief, inspect its ID then pause it:

    .\.venv\Scripts\python.exe -m agentforge.autopilot_v13 report
    .\.venv\Scripts\python.exe -m agentforge.quality_v14 pause-schedule SCHEDULE_ID --confirm-pause

The pause does not delete tasks or other queued jobs. New schedules require a clear business-context match.

## Security, quota and production limits

- Only existing proposal-only skills media.copy_draft and web.create are delegated.
- V1.3 atomic UTC daily model-call reservation, existing quota and no automatic replay are retained.
- Review records store SHA, task ID, decision and reason codes, not raw prompts or model output.
- Profile SHA is a content digest, not a cryptographic identity/authentication signature.
- Model call limit is an estimated invocation count, NOT provider-enforced financial/token spend.
- No recurring self-created objectives, OS service, public network server, customer CRM or unattended deployment.
- Emergency Pause prevents new dispatch, but cannot interrupt in-flight provider requests.
- Run Python unittest discovery and existing Node frontend suite on Windows. Test mocks do not prove live provider billing or business conversion.
