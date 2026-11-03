import json
from pathlib import Path

from agentforge.source_reader import REPORTS


ROOT = Path(__file__).resolve().parents[2]
OPPORTUNITIES = ROOT / "data" / "opportunities"

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


def supported(item):
    if not isinstance(item, dict):
        return False

    refs = item.get("evidence_refs", [])

    return (
        item.get("status") == "SUPPORTED"
        and isinstance(refs, list)
        and any(isinstance(ref, str) and ref.strip() for ref in refs)
    )


def evaluate(inputs, competitor_data):
    checks = inputs.get("checks", {})

    missing = [
        key
        for key in REQUIRED
        if not supported(checks.get(key))
    ]

    blocker = inputs.get("hard_blocker", {})
    blocker_refs = blocker.get("evidence_refs", [])

    blocker_confirmed = (
        blocker.get("confirmed") is True
        and isinstance(blocker_refs, list)
        and any(isinstance(ref, str) and ref.strip()
                for ref in blocker_refs)
    )

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
        reason = "An evidenced hard blocker was supplied"
    elif not missing:
        decision = "GO_TO_EXPERIMENT"
        reason = "All required evidence checks were marked supported"
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

    result = evaluate(inputs, competitor_data)

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