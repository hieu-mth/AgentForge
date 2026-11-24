# Studio V3 production quality baseline

Baseline `0251f47`. Owner production `9c7a083eaaa34c1386887d19a7a0135b` is in `REVIEW`. Its final MP4 and receipt passed SHA verification. The receipt reports 360 decoded frames at 24 FPS and 512 × 288, corresponding to 15 seconds. Creative quality remains `NOT_VERIFIED`.

## Reproduce the local evidence

```powershell
.\.venv\Scripts\python.exe -m scripts.storyboard_quality_baseline 9c7a083eaaa34c1386887d19a7a0135b build/v3-baseline-review
```

The command reads SQLite and verified media and writes a contact sheet, first/middle/last PNGs for every motion clip and a JSON snapshot into a new local folder. The snapshot includes Owner content and stays outside Git. Extracted frames use the source clips before final timeline trimming.

| Priority | Evidence | Layer |
| --- | --- | --- |
| P1 | Cat silhouette and fur markings, furniture layout and box size drift across shots 1–6. | Image continuity. The source stills and workflow must be reviewed before assigning cause. |
| P1 | The first six shots revisit approach and contact. Checkpointed descriptions already repeat parts of those actions. | Creative planning and continuity. |
| P1 | In shot 7 the box shape changes as the ball emerges. | Motion, source conditioning or both. |
| P2 | Shots 7–9 communicate ball emergence, reaction and contact in order. Prop scale and room layout shift at the cuts. | Storytelling and editing continuity. |

Compare later runs with the same script using ordered action coverage, identity and prop consistency, end-to-start pose continuity, readable motion, cut intention, decoded frame count, retries and peak resources. Smoothness, peak resources for the whole run and an Owner quality decision require separate evidence.
