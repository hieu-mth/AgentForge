# AgentForge C7C — Customer Problem Corroboration

C7C adds a **small, local-only registration gate** for the `customer_problem` scope in Evaluation. It supports **exactly two distinct, owner-reviewed, consented first-hand interviews** from the same research opportunity. The owner must manually attest (1) that the interviews were with separate real people, and (2) that both statements describe the same relevant business problem.

**Limits of evidence:** Two separate self-reported accounts are *corroboration*, **not independent verification of facts, real demand, willingness to pay, or completed sales**. SHA-256 detects later file changes, not whether the original interview was fabricated. C7C cannot verify participant identity. Even registered customer-problem evidence does not authorize product launches, communication, tool execution, spending, or GO by itself.

The registry's reader checks source interview and C7B review fingerprints **on each evaluation**. Altering the source afterward invalidates that reference. The files are local and not protected against an attacker controlling the computer. Do not insert fictional data for the purpose of registration.

## Commands (PowerShell)

```powershell
cd E:\Projects\AgentForge
.\.venv\Scripts\python.exe -m agentforge.customer_problem_evidence inspect research-d3188c6a
```

If no *real* interview has been captured, this reports `retained_count: 0` and `ready_for_owner_corroboration: false`. **Stop there.** The older synthetic `shop_01` record, if captured/rejected, remains disqualified and unchanged.

Only **after two genuine interviews**, consented C7A capture and C7B `retain` with owner confirmation, and manual comparison of the two problems:

```powershell
.\.venv\Scripts\python.exe -m agentforge.customer_problem_evidence register research-d3188c6a shop_02 shop_03 --note "I personally compared two distinct interviews about the same order reconciliation problem; neither establishes sales." --confirm-independent-interviews --confirm-same-problem
```

The sample participant codes are examples, not fabricated interviews to create. A registered evidence file is stored under `data/opportunities/evidence/` and indexed in `data/opportunities/evidence_index.json` with `supports: ["customer_problem"]` only. Review records are not changed. Neither `willingness_to_pay` nor `unit_economics` can use this reference. The evaluator still returns `RESEARCH_MORE` until *all other* requirements have their own eligible evidence and budget/owner conditions are met.

Tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_customer_problem_evidence.py" -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

C7C adds 21 regression tests. Expected total after C7B's 177: **198**. Run and confirm locally before committing.
