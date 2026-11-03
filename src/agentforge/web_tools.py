from ddgs import DDGS


def web_search(query: str, limit: int = 4) -> list[dict]:
    if not isinstance(query, str) or not query.strip():
        raise ValueError("Search query cannot be empty")

    if not 1 <= limit <= 5:
        raise ValueError("Search limit must be between 1 and 5")

    results = DDGS(timeout=20).text(
        query[:200],
        region="vn-vi",
        max_results=limit
    )

    cleaned = []

    for item in results or []:
        url = item.get("href", "")

        if not url.startswith(("https://", "http://")):
            continue

        cleaned.append({
            "title": str(item.get("title", ""))[:200],
            "url": url,
            "snippet": str(item.get("body", ""))[:600]
        })

    return cleaned
