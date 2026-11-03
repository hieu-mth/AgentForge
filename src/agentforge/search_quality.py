import unicodedata
from urllib.parse import urlsplit


COMMUNITY_DOMAINS = ("voz.vn", "reddit.com")

PRODUCT_TERMS = ("excel", "spreadsheet", "google sheets")

PROBLEM_TERMS = (
    "ton kho",
    "quan ly kho",
    "don hang",
    "ban hang",
    "loi nhuan",
    "inventory",
    "stock",
    "orders",
    "profit",
)


def normalize(text):
    text = text.lower().replace("đ", "d")
    return "".join(
        ch for ch in unicodedata.normalize("NFD", text)
        if unicodedata.category(ch) != "Mn"
    )


def classify_community_hit(item):
    url = item.get("url", "")
    host = (urlsplit(url).hostname or "").lower()

    if not any(
        host == domain or host.endswith("." + domain)
        for domain in COMMUNITY_DOMAINS
    ):
        return "REJECT_NOT_COMMUNITY"

    content = normalize(
        item.get("title", "") + " " + item.get("snippet", "")
    )

    if not any(term in content for term in PRODUCT_TERMS):
        return "REJECT_OFF_TOPIC"

    if not any(term in content for term in PROBLEM_TERMS):
        return "REJECT_OFF_TOPIC"

    return "REVIEW_ONLY_NOT_VERIFIED"