# AI domain

This top-level directory is the **AI capability and architecture entrypoint**.
The currently stable Python runtime remains under \`src/agentforge/\` to preserve
SQLite history, installed entrypoints, existing imports and S1–S5 contracts.

## Current module ownership

| Capability | Existing stable implementation |
|---|---|
| Provider/model registry | \`src/agentforge/model.py\`, \`model_registry.py\` |
| Natural-language intake | \`src/agentforge/prompt_intake.py\` |
| Planning & supervised execution | \`src/agentforge/brain_planner.py\`, \`brain_runner.py\` |
| Skill registry & permissions | \`src/agentforge/skill_registry.py\`, \`skill_runner.py\` |
| Website/product AI | \`src/agentforge/product_builder.py\`, \`website_feedback.py\` |
| Local raster AI adapter | \`src/agentforge/image_studio_v24.py\` |
| Quality and review | \`src/agentforge/quality_v14.py\` |

**Do not import files by their folder path.** New Python subpackages should be
\`src/agentforge/ai/\`, not bare \`ai/\`, because the installed package remains
\`agentforge\`. Future moves must add compatibility import wrappers, migrate
one bounded domain at a time, and pass regression/acceptance on Windows before
removing any old path.

This directory is for AI architecture, role manifests and future workflow
definitions. It is **not a second executable AI runtime**.
