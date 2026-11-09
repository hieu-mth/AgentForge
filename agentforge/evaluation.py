import json
from pathlib import Path

from agentforge.source_reader import REPORTS
from agentforge.evidence_registry import valid_references_for_opportunity


from agentforge.paths import REPOSITORY_ROOT

ROOT = REPOSITORY_ROOT
OPPORTUNITIES = ROOT / "data" / "opportunities"
EVIDENCE_DIR = OPPORTUNITIES / "evidence"

REQUIRED = {
    "customer_problem": "Problem confirmed by target customers",
    "willingness_to_pay": "Evidence customers may pay",
    "differentiation": "Clear advantage over free alternatives",
    "distribution": "Feasible customer acquisition channel",
    "unit_economics": "Estimated costs and margins",
}


def default_inputs():
    return {
        "opportunity": "Excel tracker for small online shops in Vietnam",
        "opportunity_id": None,  # Must match the registered evidence opportunity.
        "checks": {
            key: {
                "status": "UNKNOWN",
                "evidence_refs": []
            }
            for key in REQUIRED
        },
        "hard_blocker": {
            "confirmed": False,
            "evidence_refs": []
        },
        "experiment": {
            "budget_cap_vnd": None,
            "owner_approved": False
        }
    }


def supported(item, scope, evidence_index, evidence_dir, opportunity_id):
    if not isinstance(item, dict):
        return False

    return (
        item.get("status") == "SUPPORTED"
        and valid_references_for_opportunity(
            item.get("evidence_refs", []),
            scope,
            evidence_index,
            evidence_dir,
            opportunity_id,
        )
    )


def evaluate(inputs, competitor_data, evidence_index=None, evidence_dir=None):
    if evidence_dir is None:
        evidence_dir = EVIDENCE_DIR

    opportunity_id = inputs.get("opportunity_id")
    checks = inputs.get("checks", {})

    missing = [
        key
        for key in REQUIRED
        if not supported(
            checks.get(key), key, evidence_index, evidence_dir, opportunity_id
        )
    ]

    blocker = inputs.get("hard_blocker", {})
    blocker_refs = blocker.get("evidence_refs", [])

    blocker_claimed = blocker.get("confirmed") is True

    blocker_confirmed = (
        blocker_claimed
        and valid_references_for_opportunity(
            blocker_refs,
            "hard_blocker",
            evidence_index,
            evidence_dir,
            opportunity_id,
        )
    )

    if blocker_claimed and not blocker_confirmed:
        missing.append("hard_blocker_evidence")

    experiment = inputs.get("experiment", {})
    budget = experiment.get("budget_cap_vnd")

    budget_defined = (
        type(budget) is int and budget >= 0
    )

    if not budget_defined:
        missing.append("experiment_budget_cap")

    if experiment.get("owner_approved") is not True:
        missing.append("owner_approval")

    vendor_quotes = []

    for competitor in competitor_data.get("competitors", []):
        for fact in competitor.get("facts", []):
            if (
                fact.get("field") == "price"
                and fact.get("quote_status") == "MATCHED_IN_PAGE"
            ):
                vendor_quotes.append({
                    "competitor": competitor.get("name"),
                    "statement": fact.get("statement"),
                    "quote": fact.get("quote")
                })

    if blocker_confirmed:
        decision = "KILL"
        reason = "An owner-reviewed hard blocker reference was resolved"
    elif not missing:
        decision = "GO_TO_EXPERIMENT"
        reason = "All required checks have owner-reviewed local evidence"
    else:
        decision = "RESEARCH_MORE"
        reason = "Insufficient evidence for a controlled experiment"

    return {
        "opportunity": inputs.get("opportunity"),
        "decision": decision,
        "reason": reason,
        "vendor_price_quotes": vendor_quotes,
        "vendor_price_quotes_are_sales_proof": False,
        "missing_requirements": missing,
        "execution_authorized": False,
        "review_note": (
            "Evidence references and classifications must be "
            "manually checked. This evaluator does not verify "
            "independent sales or authorize spending."
        )
    }


def main():
    OPPORTUNITIES.mkdir(parents=True, exist_ok=True)

    input_path = OPPORTUNITIES / "excel_tracker_inputs.json"
    output_path = OPPORTUNITIES / "excel_tracker_decision.json"

    if not input_path.exists():
        input_path.write_text(
            json.dumps(default_inputs(), ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        print("CREATED:", input_path)

    inputs = json.loads(input_path.read_text(encoding="utf-8"))

    competitor_path = REPORTS / "competitor_facts.json"

    competitor_data = json.loads(
        competitor_path.read_text(encoding="utf-8")
    )

    evidence_index_path = OPPORTUNITIES / "evidence_index.json"

    evidence_index = (
        json.loads(evidence_index_path.read_text(encoding="utf-8"))
        if evidence_index_path.is_file()
        else {}
    )

    result = evaluate(inputs, competitor_data, evidence_index)

    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print("OPPORTUNITY:", result["opportunity"])
    print("DECISION:", result["decision"])
    print("VENDOR PRICE QUOTES:", len(result["vendor_price_quotes"]))
    print("MISSING REQUIREMENTS:")

    for item in result["missing_requirements"]:
        print(" -", item)

    print("EXECUTION AUTHORIZED:", result["execution_authorized"])
    print("SAVED:", output_path)


if __name__ == "__main__":
    main()