"""Owner-approved adaptive analysis of a bounded Markdown directory."""

import hashlib
import re
from itertools import islice

from agentforge import gateway, ops_control, research_report

DIRECTORY = r"[a-zA-Z0-9_-]+(?:/[a-zA-Z0-9_-]+)*"
FILENAME = re.compile(r"[a-zA-Z0-9_.-]{1,116}\.md\Z", re.IGNORECASE)
OUTPUT = re.compile(r"agent-reports/[a-f0-9]{32}\.md\Z")
COMMAND = {
    "tool": {"type": "string", "enum": ["read", "search"]},
    "file": {"type": "integer"},
    "start_line": {"type": "integer"},
    "query": {"type": "string"},
}
MAX_FILES = 20
MAX_EXCERPT = 1200


def validate_request(prompt, directory, path):
    if (not isinstance(prompt, str) or not 20 <= len(prompt) <= 1500
            or any(ord(ch) < 32 and ch not in "\n\t" for ch in prompt)):
        raise ValueError("Workspace analysis requires a brief of 20–1500 characters")
    if (not isinstance(directory, str) or len(directory) > 120
            or not re.fullmatch(DIRECTORY, directory)
            or directory.split("/")[0].casefold() == "agent-reports"
            or not gateway.safe_path(directory).is_dir()):
        raise ValueError("Choose an existing workspace input directory")
    if not isinstance(path, str) or not OUTPUT.fullmatch(path):
        raise ValueError("Invalid workspace agent report destination")
    gateway.validate_report(path, "pending")


def _inventory(directory):
    directory_path = gateway.safe_path(directory)
    names = []
    for entry in islice(directory_path.iterdir(), 200):
        if (not entry.name.startswith(".") and FILENAME.fullmatch(entry.name)
                and not entry.is_symlink()
                and not (hasattr(entry, "is_junction") and entry.is_junction())
                and entry.is_file()):
            names.append(entry.name)
    return sorted(names)[:MAX_FILES]


def _command(value, files):
    tool, index = value["tool"], value["file"]
    line, query = value["start_line"], value["query"]
    if (type(index) is not int or type(line) is not int or not isinstance(query, str)
            or len(query) > 96 or (query and not query.isprintable())):
        raise ValueError("AGENT_INVALID_ACTION")
    if tool == "read" and 0 <= index < len(files) and 1 <= line <= 4096 and not query:
        return tool, index, line, query
    if (tool == "search" and (index == -1 or 0 <= index < len(files))
            and line == 0 and len(query.strip()) >= 2):
        return tool, index, line, query.strip().casefold()
    raise ValueError("AGENT_INVALID_ACTION")


def _observe(action, directory, files, evidence, trace):
    tool, index, start, query = action
    indexes = range(len(files)) if index == -1 else (index,)
    hits = []
    skipped = 0
    for file in indexes:
        try:
            data = gateway.read_file(f"{directory}/{files[file]}")
        except (FileNotFoundError, ValueError):
            skipped += 1
            continue
        lines = data.splitlines()
        if tool == "search":
            line = next((i for i, text in enumerate(lines, 1) if query in text.casefold()), None)
        else:
            line = start if start <= len(lines) else None
        if line is None:
            continue
        excerpt = "\n".join(lines[line - 1:line + 7])[:MAX_EXCERPT].strip()
        if not excerpt:
            continue
        evidence.append({"id": len(evidence) + 1, "file": file, "line": line,
                         "excerpt": excerpt,
                         "text_sha256": hashlib.sha256(data.encode("utf-8")).hexdigest()})
        hits.append(evidence[-1]["id"])
        if len(hits) == 3:
            break
    trace.append({"tool": tool, "matches": len(hits), "skipped": skipped,
                  "file": index, "evidence_ids": hits})


def run(prompt, directory, path):
    """Run two result-driven tool choices and one checked synthesis."""
    validate_request(prompt, directory, path)
    files = _inventory(directory)
    if not files:
        raise ValueError("AGENT_NO_MARKDOWN_IN_SCOPE")
    runtime = research_report._runtime(allow_cloud=False)
    evidence, trace = [], []
    choices = set()
    for _ in range(2):
        ops_control.require_active()
        decision = research_report._ask(runtime, {
            "action": "Choose a workspace operation, adapting to the previous result. "
                      "read: file index and positive start_line, empty query. "
                      "search: file index or -1 for all, start_line 0, literal query. "
                      "Use a different operation or argument set on the second turn.",
            "brief": prompt, "files": files, "prior_actions": [dict(x) for x in trace],
            "evidence": evidence,
        }, COMMAND, timeout_seconds=75, max_output_tokens=256)
        action = _command(decision, files)
        if action in choices:
            raise ValueError("AGENT_REPEATED_ACTION")
        choices.add(action)
        _observe(action, directory, files, evidence, trace)
    if not evidence:
        raise ValueError("AGENT_NO_EVIDENCE")
    ops_control.require_active()
    body = research_report._ask(runtime, {
        "action": "Write a Markdown report under 3500 UTF-8 bytes. Cite evidence as [1], "
                  "[2], etc., using existing evidence ids only. "
                  "Distinguish facts from findings and mention gaps. Do not add links.",
        "brief": prompt, "files": files, "evidence": evidence, "operations": trace,
    }, {"markdown": {"type": "string"}}, timeout_seconds=90,
        max_output_tokens=1800)["markdown"]
    if not isinstance(body, str):
        raise ValueError("AGENT_INVALID_REPORT")
    ids = set(re.findall(r"\[(\d+)\]", body))
    if (not ids or ids - {str(item["id"]) for item in evidence}
            or len(body.encode("utf-8")) > 3500 or "://" in body or "www." in body.lower()
            or re.search(r"\]\s*\(|[<>]|[\x00-\x08\x0b-\x1f]", body)
            or re.search(r"(?m)^\s*\[[^\]\n]+\]:", body)):
        raise ValueError("AGENT_INVALID_REPORT")
    sources = [
        f'[{item["id"]}] `workspace/{directory}/{files[item["file"]]}` '
        f'dòng {item["line"]} · SHA-256 văn bản {item["text_sha256"]}'
        for item in evidence if str(item["id"]) in ids
    ]
    ops_control.require_active()
    receipt = gateway.write_verified_report(path, body.strip() + "\n\n## Tài liệu đã đọc\n\n"
                                            + "\n\n".join(sources) + "\n")
    return {**receipt, "model": runtime["model"], "trace": trace,
            "citations_checked": len(sources)}
