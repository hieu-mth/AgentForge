import json
from datetime import datetime, timezone

from agentforge.source_reader import REPORTS, fetch_page


CANDIDATES = [
    {
        "id": "C1",
        "name": "ZoneTech",
        "url": "https://zonetech.com.vn/tai-lieu-mien-phi/file-excel/quan-ly-kho-ban-hang/"
    },
    {
        "id": "C2",
        "name": "WPRO",
        "url": "https://wpro.vn/2-0/"
    },
    {
        "id": "C3",
        "name": "Excel Tu Dong Hoa",
        "url": (
            "https://www.exceltudonghoa.com/"
            "2026/02/file-quan-ly-kho-va-ban-hang.html"
        )
    }
]


def main():
    REPORTS.mkdir(parents=True, exist_ok=True)
    records = []

    for candidate in CANDIDATES:
        print(
            "CHECKING:",
            candidate["id"],
            candidate["name"],
            flush=True
        )

        record = dict(candidate)
        record["checked_at"] = datetime.now(
            timezone.utc
        ).isoformat()

        try:
            page = fetch_page(candidate["url"])
            record.update(page)
            record["status"] = "FETCHED_NOT_FACT_CHECKED"

            print(
                "  FETCH: PASS",
                "| Characters:",
                page["extracted_characters"]
            )

        except Exception as error:
            record["status"] = "FETCH_FAILED"
            record["error"] = (
                f"{type(error).__name__}: {str(error)[:200]}"
            )

            print("  FETCH: FAILED", record["error"])

        records.append(record)

    output = REPORTS / "competitor_pages.json"

    output.write_text(
        json.dumps(
            {"competitors": records},
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    successful = sum(
        item["status"] == "FETCHED_NOT_FACT_CHECKED"
        for item in records
    )

    print("\nCOMPETITOR RESEARCH COMPLETED")
    print("PAGES FETCHED:", successful, "/", len(records))
    print("SAVED:", output)


if __name__ == "__main__":
    main()