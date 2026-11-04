"""Stage quote-matched observations for manual owner review; no approvals."""

import argparse
import json

from agentforge import task_inbox
from agentforge.source_review import FIELDS


def prepare_candidates(task_id):
    task = task_inbox.read_task(task_id)

    if task.get("status") != "PROPOSED":
        raise ValueError("Only proposed tasks can stage candidates")

    report_path = task_inbox.DATA_DIR / "reviews" / f"{task_id}.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))

    if (
        not isinstance(report, dict)
        or report.get("task_id") != task_id
        or report.get("opportunity_id") != task.get("opportunity_id")
        or report.get("review_status") != "QUOTE_REVIEW_ONLY"
        or any(
            report.get(key) is not False
            for key in (
                "customer_demand_verified",
                "revenue_verified",
                "execution_authorized",
                "spending_authorized",
            )
        )
    ):
        raise ValueError("Invalid or unsupported source review report")

    approved_urls = task.get("source_urls")
    reviews = report.get("source_reviews")

    if (
        not isinstance(approved_urls, list)
        or not approved_urls
        or not all(isinstance(url, str) for url in approved_urls)
        or not isinstance(reviews, list)
    ):
        raise ValueError("Invalid review sources")

    seen_urls = set()
    candidates = []

    for review in reviews:
        if not isinstance(review, dict):
            raise ValueError("Invalid review entry")

        url = review.get("url")

        if url not in approved_urls or url in seen_urls:
            raise ValueError("Unapproved or repeated review URL")

        seen_urls.add(url)

        observations = review.get("observations")

        if not isinstance(observations, list):
            raise ValueError("Invalid observations")

        if review.get("status") != "QUOTES_CHECKED_NOT_FACT_CHECKED":
            if observations:
                raise ValueError("Observations on an unreviewed source")
            continue

        for observation in observations:
            if not isinstance(observation, dict):
                raise ValueError("Invalid observation")

            if observation.get("quote_status") != "MATCHED_IN_PAGE":
                continue

            field = observation.get("field")
            statement = observation.get("statement")
            quote = observation.get("quote")

            if (
                observation.get("independently_verified") is not False
                or field not in FIELDS
                or not isinstance(statement, str)
                or not statement.strip()
                or not isinstance(quote, str)
                or not 30 <= len(quote.strip()) <= 300
            ):
                raise ValueError("Invalid matched observation")

            candidates.append({
                "candidate_id": f"C{len(candidates) + 1}",
                "source_url": url,
                "field": field,
                "statement": statement,
                "quote": quote,
                "quote_status": "MATCHED_IN_PAGE",
                "independently_verified": False,
                "owner_reviewed": False,
                "supports": [],
            })

    if not candidates or report.get("matched_quotes") != len(candidates):
        raise ValueError("No consistent matched quotes to stage")

    document = {
        "task_id": task_id,
        "opportunity_id": task["opportunity_id"],
        "status": "PENDING_OWNER_REVIEW",
        "owner_reviewed": False,
        "execution_authorized": False,
        "spending_authorized": False,
        "source_review_file": f"reviews/{task_id}.json",
        "candidates": candidates,
    }

    output = (
        task_inbox.DATA_DIR
        / "evidence_candidates"
        / f"{task_id}.json"
    )

    output.parent.mkdir(parents=True, exist_ok=True)

    # Never overwrite a previous handoff.
    with output.open("x", encoding="utf-8") as file:
        json.dump(document, file, ensure_ascii=False, indent=2)

    return output


def main():
    parser = argparse.ArgumentParser(
        description="Stage source quotes for owner review"
    )
    parser.add_argument("task_id")
    args = parser.parse_args()

    output = prepare_candidates(args.task_id)

    print("STATUS: PENDING_OWNER_REVIEW")
    print("OWNER REVIEWED: False")
    print("EXECUTION AUTHORIZED: False")
    print("SAVED:", output)


if __name__ == "__main__":
    main()
