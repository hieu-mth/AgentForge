# NovaMart — reviewed React template (reference demo)

This is a **hand-reviewed functional reference app**, not an AI-generated
application and not a working ecommerce store. It is actively used as the trusted scaffold for marketplace and experimental
React app proposals in `agentforge/domains/webapps/`. Keep its npm lockfile,
React source and test contracts intact. Editing it changes the reference
toolchain for **new** proposals; old proposals retain their original SHA.

### Windows PowerShell

\`\`\`powershell
cd D:\AgentForge\templates\novamart
npm.cmd install
npm.cmd test
npm.cmd run build
npm.cmd run dev
\`\`\`

Then open http://127.0.0.1:5184.

Everything is local: sample product data, CSS illustrations, search, filters,
sorting, product detail dialog and cart state. Nothing is ordered, purchased,
posted or collected. No payment, authentication, API, remote assets, analytics,
real reviews, real promotions or genuine product photos.

The application **does not run in the AgentForge Owner dashboard** and does
not gain any access to AgentForge credentials. Starting Vite and installing
dependencies remain explicit manual Owner actions for this milestone.
Production dependency review and sandboxed execution are future V4 milestones.

Acceptance: search, select category, filter and sort, open product detail, add
to cart, increase/decrease quantities and remove items; verify cart totals and
mobile layout. \`npm test\` exercises pure commerce logic; \`npm run build\`
checks React compilation. CI runs a trusted Microsoft Edge interaction smoke on this template.
This does **not** verify browser execution or isolation of AI-generated source;
generated code remains untrusted and cannot run in the Owner browser origin.
