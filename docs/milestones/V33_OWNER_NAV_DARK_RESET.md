# V3.3 owner review: dark default, sidebar, safe fresh start

The React sidebar is now Overview-first, the old UI link is removed, and the desktop collapse button is a rotating chevron on the right edge of the sidebar. Previously bookmarked sections still work. The Giao việc 0/600 counter is in the footer, under the divider rather than overlapping it. First-time users start in dark theme; an explicitly saved light theme remains respected.

## Safe local data cleanup

The user's SQLite databases, task history, campaign data and generated products are stored only on their Windows computer and deliberately excluded from Git. Updating GitHub cannot delete or inspect these files.

Stop **all** AgentForge Python servers, workers and schedulers first. Then run:

    cd D:\AgentForge
    .\.venv\Scripts\python.exe scripts\archive_local_state.py report

For a completely fresh local runtime, after reviewing the scope, explicitly run:

    .\.venv\Scripts\python.exe scripts\archive_local_state.py archive --confirm-stopped --confirm-archive ARCHIVE_LOCAL_STATE

This moves complete data/ and workspace/ directories outside the Git checkout, into a timestamped sibling directory such as D:\AgentForge-local-state-archives\state-YYYYMMDDTHHMMSSZ-xxxxxxxx. The command reports the actual archive ID. No files are permanently deleted, and the Dashboard will start with fresh state on the next launch.

To restore, stop all services, ensure data/ and workspace/ are both absent (archive any NEW active state separately first), then:

    .\.venv\Scripts\python.exe scripts\archive_local_state.py restore ARCHIVE_ID --confirm-stopped --confirm-restore RESTORE_LOCAL_STATE

Restore refuses to overwrite either active folder. Never manually delete customer data to force a restore.

The archive is local and unencrypted; protect it using Windows access controls. It is **not** a disaster-recovery cloud backup and does not free disk space. Credentials in .env, Ollama model weights, packages, Git, and source code are not affected. For independent SQLite ZIP backups continue using the existing ops_backup utility.

## UI test on Windows

    cd D:\AgentForge
    git pull --ff-only origin main
    .\.venv\Scripts\python.exe -m unittest tests.test_archive_local_state -v
    cd ui\dashboard
    npm.cmd install
    npm.cmd run test:navigation
    npm.cmd run build

Then restart the Python backend and open http://127.0.0.1:8780/dashboard/.
The state archival command is strictly optional and should only be run when the owner chooses a fresh start.
