# Studio Creative Director

New motion drafts with authored scene headings and the current duration mode use Creative Director. Existing drafts, free-form ideas and still productions retain their existing planner. SQLite requires no migration. The storyboard model proposes ordered groups of action IDs, camera direction and relative duration. Python validates coverage and compiles runtime-sized segments within the existing production frame and segment budget.

The approval digest includes the compiled plan, the segment storyboard and the existing model and motion identity. On resume the stored plan is recompiled against the pinned output profile and the storyboard frame counts are rechecked. Editing segment text updates the storyboard digest and uses the existing asset invalidation rules. Authored scene boundaries and the creative segment layout stay fixed during segment edits. A new production is required to propose a different layout.

## Planning repair and limitations

Incomplete or out-of-order action coverage receives at most one contextual model revision; invalid coverage after that stops planning. Segment prompts distinguish prepare, progress and complete for continued actions. Exact duplicate descriptions or motion prompts receive bounded repair. These controls do not establish semantic or visual continuity.

## Video comparison

On an executable rollback, leave drafts using the creative plan paused until the compatible build is restored. Older builds do not understand this layout or its approval digest. Registry rollback to the exact pinned profile remains supported by the existing dispatch guard.

Use separate draft, visual and motion ledgers and workspace paths for the baseline and candidate. Hold the script, enabled Model Hub assignments, workflow, encoder and rendering settings constant. Approve each storyboard through the existing Owner gate before media dispatch.

Run the resource sampler alongside each test draft. Use the approved test production ID and redirect JSONL to the test evidence folder.

```powershell
.\.venv\Scripts\python.exe -m scripts.studio_resource_baseline <test-production-id> --sample-seconds 600
```

The samples are interval observations and can miss shorter peaks. Use the saved image and motion receipts and the final timeline to separate inference, queue and render duration. Export a contact sheet and report from each completed production with `scripts.storyboard_quality_baseline`, and verify the saved images, clips and final MP4 with `scripts.studio_technical_qa`.

Record action coverage, count purposeful angles, and compare each adjacent segment boundary for subject, prop, pose and camera continuity. A technical pass leaves creative quality unverified. Frame chaining, conditioning and targeted regeneration require evidence from the resulting video before adoption.
