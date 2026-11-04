# AgentForge C7B — Customer Evidence Review

C7B is **local-only**. It consumes **captured C7A records** and writes one immutable owner decision per participant. No AI, network, customer outreach, evidence registration, GO/KILL, spending or tool execution.

## Safety model

- `CAPTURED_UNVERIFIED`: an owner-entered C7A interview note, possibly still inaccurate. C7B **cannot determine whether an interview actually happened**.
- `RETAINED_FIRSTHAND_CLAIM`: the owner explicitly attests they personally checked that the interview is real, the quote reflects its context, and consent was recorded. This remains a **first-hand account, not independently verified business truth**.
- `NEEDS_FOLLOWUP`: context or provenance is not yet sufficient.
- `REJECTED`: e.g. demonstration data, mismatched opportunity, unreliable quote.
- All outputs always set `customer_problem_verified=false`, `willingness_to_pay_verified=false`, `payment_verified=false`, `evidence_eligible=false`, `supports=[]`, `execution_authorized=false`, and `spending_authorized=false`.
- SHA-256 links the review to the exact captured JSON bytes and detects **later modifications** when the review is read. It is not proof that the original interview was genuine.
- Review files go to `data/company/customer_validation/reviews/<opportunity_id>/<participant_code>.json`, ignored by Git. Decisions cannot be overwritten by the CLI.

## Commands (PowerShell)

```powershell
cd E:\Projects\AgentForge

# If no real interview has been captured, summary still works and displays 0.
.\.venv\Scripts\python.exe -m agentforge.customer_evidence_review summary research-d3188c6a

# Only after C7A capture with real interview/consent:
.\.venv\Scripts\python.exe -m agentforge.customer_evidence_review inspect research-d3188c6a shop_01

# If this was a simulated example accidentally captured:
.\.venv\Scripts\python.exe -m agentforge.customer_evidence_review reject research-d3188c6a shop_01 --note "This record is only a simulated sample, not an actual customer interview."

# If details require follow-up rather than a categorical rejection:
.\.venv\Scripts\python.exe -m agentforge.customer_evidence_review followup research-d3188c6a shop_01 --note "Interview details need corroboration and quote context review."

# For REAL first-hand interviews only. Review original local JSON and context first.
.\.venv\Scripts\python.exe -m agentforge.customer_evidence_review retain research-d3188c6a shop_01 --note "I personally confirmed the interview and checked the anonymized quote in context." --confirm-firsthand-interview --confirm-quote-context
```

Use **one** of `retain`, `followup`, or `reject` for a participant, never all three. A saved decision is immutable; if it was wrong, do not edit the record by hand. Preserve it for audit and investigate before a future correction workflow.

C7B does **not** perform identity verification, interview transcription checks, payment verification or independent corroboration. It cannot conclusively distinguish fabricated data from real data. The CLI is a record of the owner's assertions, not a truth oracle. Do not put personal information (names, email addresses, phone numbers, detailed chat history, payment credentials) in quotes or notes. C7A's input filter only catches a limited subset of sensitive strings.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_customer_evidence_review.py" -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

20 new tests in C7B; expected total after C7A's 157 is 177. The full count needs confirmation on the target Windows machine.
