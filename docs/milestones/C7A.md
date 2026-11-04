# AgentForge C7A — Customer Validation Intake

Checkpoint: `d70fb86` (C6C) or later. This is **additive**: no existing source files or interview decisions are modified.

The new module is offline-only and takes **no action to contact people**. It saves first-hand, owner-entered notes as `CAPTURED_UNVERIFIED`, with **no** Evidence Registry references or permission to spend/execute. `VERBAL_INTEREST` / `PAST_PAYMENT_CLAIM` are **claims**, never verified sales or willingness-to-pay.

Run from project root in Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m agentforge.customer_validation questions
.\.venv\Scripts\python.exe -m agentforge.customer_validation summary research-d3188c6a

# ONLY after you have actually interviewed someone and have permission to retain an anonymous quote:
.\.venv\Scripts\python.exe -m agentforge.customer_validation new research-d3188c6a shop_01
notepad .\data\company\customer_validation\drafts\research-d3188c6a\shop_01.json

# Edit the JSON manually. Keep actual dates and customer wording; do not invent answers.
# source_channel = IN_PERSON / CALL / CHAT
# frequency = DAILY / WEEKLY / MONTHLY / RARE / UNKNOWN
# payment_signal = NOT_DISCUSSED / VERBAL_INTEREST / DECLINED / PAST_PAYMENT_CLAIM
# Include interview_date YYYY-MM-DD, business_context, problem_quote,
# current_workaround, owner_note. Do not edit identity or status fields.

.\.venv\Scripts\python.exe -m agentforge.customer_validation check research-d3188c6a shop_01
.\.venv\Scripts\python.exe -m agentforge.customer_validation capture research-d3188c6a shop_01 --confirm-consent
.\.venv\Scripts\python.exe -m agentforge.customer_validation summary research-d3188c6a
```

Privacy: only store anonymized notes with permission; do not include phone numbers, names, emails, customer IDs, or screenshots of private chats. The module performs limited input checks, **not** comprehensive PII detection. `data/` is already ignored by Git, but local files still need normal device security. If there has been no real interview, **do not fabricate or capture one**: start with the `questions` and `summary` commands only.

Tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_customer_validation.py" -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Expected new tests: 15. Expected total if C6C was 142: 157. Do not commit local interview JSON files.
