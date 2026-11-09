"""Local-first handoff from research reports to manual source review."""

import argparse
import json
import re
from pathlib import Path

from agentforge import source_reader, task_inbox


ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "data" / "research"

RESEARCH_ID_RE = re.compile(r"[a-f0-9]{32}\Z")
SOURCE_ID_RE = re.compile(r"S[1-9][0-9]{0,3}\Z")


def propose_review(research_id, source_ids):
    if (
        not isinstance(research_id, str)
        or not RESEARCH_ID_RE.fullmatch(research_id)
    ):
        raise ValueError("Invalid research ID")

    if (
        not isinstance(source_ids, (list, tuple))
        or not 1 <= len(source_ids) <= 5
        or any(
            not isinstance(sid, str)
            or not SOURCE_ID_RE.fullmatch(sid)
            for sid in source_ids
        )
        or len(set(source_ids)) != len(source_ids)
    ):
        raise ValueError("Select 1 to 5 unique source IDs")

    report_path = REPORTS / f"{research_id}.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))

    if (
        not isinstance(report, dict)
        or report.get("research_id") != research_id
        or report.get("status") != "LEADS_ONLY_NOT_VERIFIED"
        or not isinstance(report.get("sources"), list)
    ):
        raise ValueError("Invalid or unsupported research report")

    source_map = {}

    for source in report["sources"]:
        if not isinstance(source, dict):
            raise ValueError("Invalid source record")

        sid = source.get("source_id")

        if not isinstance(sid, str) or sid in source_map:
            raise ValueError("Invalid or duplicate source ID")

        source_map[sid] = source.get("url")

    urls = []

    for sid in source_ids:
        if sid not in source_map:
            raise ValueError(f"Source ID not found: {sid}")

        url = source_map[sid]

        # Syntax validation only. No network request.
        source_reader.validate_public_https_url(url)

        if url in urls:
            raise ValueError("Duplicate source URL")

        urls.append(url)

    task_id = f"{research_id}-source-review"

    task = {
        "task_id": task_id,
        "opportunity_id": f"research-{research_id[:8]}",
        "research_id": research_id,
        "source_ids": list(source_ids),
        "kind": "SOURCE_REVIEW",
        "status": "PROPOSED",
        "source_urls": urls,
        "execution_authorized": False,
        "spending_authorized": False,
    }

    path = task_inbox.task_path(task_id)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Exclusive create: never overwrite an existing task.
    with path.open("x", encoding="utf-8") as file:
        json.dump(task, file, ensure_ascii=False, indent=2)

    return task


def main():
    parser = argparse.ArgumentParser(
        description="AgentForge Company Workflow"
    )

    commands = parser.add_subparsers(
        dest="command",
        required=True,
    )

    propose = commands.add_parser(
        "propose-review",
        help="Create a manual review task from research sources",
    )

    propose.add_argument("research_id")
    propose.add_argument(
        "--source-id",
        action="append",
        required=True,
    )

    args = parser.parse_args()

    if args.command == "propose-review":
        task = propose_review(
            args.research_id,
            args.source_id,
        )

        print("TASK ID:", task["task_id"])
        print("STATUS:", task["status"])
        print("SOURCES:", len(task["source_urls"]))
        print("EXECUTION AUTHORIZED: False")
        print("SPENDING AUTHORIZED: False")
        print(
            "NEXT: python -m agentforge.source_review inspect",
            task["task_id"],
        )


if __name__ == "__main__":
    main()
