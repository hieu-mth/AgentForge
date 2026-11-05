# V3.2 — React operations and owner workflow parity

All day-to-day owner screens now have native React / Ant Design interfaces:

- Projects & Files: bounded local artifact inventory, ComfyUI checkpoint
  health, single-image generation, job status, SHA-verified PNG owner preview,
  explicit image review and local HTML backup + attach.
- AI & Video Review: inspected-session storyboard content, approvals/rejections
  bound to exact SHA; local MP4 review requires owner attestation after opening
  file in Windows. **No video streaming or automatic publication**.
- Schedules: list, pause/resume, guarded read-only schedule creation and
  explicit tick. No automatic model/workflow privilege elevation.
- Operations: state/daemon heartbeat, pause/resume with explicit confirmation.
- Intelligence: saved dataset provenance and row counts (read-only).
- Growth: campaign metrics and local campaign creation with demo vs owner data
  separated. No platform spending or real-profit claims.
- Settings: prompt intake role/call policy and Autopilot quota, independent
  from provider billing; both require owner confirmation.
- Owner Memory: local evidence-linked note list and revision form.
- Team, Channels and Finance remain read-only until verified integration exists.

**Architecture:** React calls the exact same authenticated/CSRF-protected
`/api/*` endpoints. It does not directly touch SQLite or spawn programs.
The new `/api/image/{job_id}/preview` serves only PNG bytes from the
existing imported image ledger, checks the immutable SHA and requires
an owner session. Arbitrary filesystem paths are not accepted.

The old Control Center remains available at `/` for diagnostics and any
unsupported edge workflows. Its removal requires a separate explicit
decision after the user's V3.3 hands-on acceptance. Advanced image/video
model and channel integration is *not* claimed to be production verified.

Quality gate: Vite React build + Python regression + PowerShell acceptance.
