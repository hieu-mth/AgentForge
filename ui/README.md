# UI applications

\`ui/dashboard/\`: separate React 19 + Ant Design 6 app, compiled with Vite.
Source is isolated from the Python HTTP backend. Its built files are served
on the existing local-only Python session at \`/dashboard/\`.

Legacy \`src/agentforge/control_center_static/\` is retained as a fallback
for workflows not migrated to React. Avoid new features there unless a
security fix is required. Migrate individual screens after contract tests.

A public Internet dashboard would need a separate auth/HTTPS/RBAC
architecture; this React UI is **not Internet-hosted** and should never be
exposed through a tunnel without that work.
