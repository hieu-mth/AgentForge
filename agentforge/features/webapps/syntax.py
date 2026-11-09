"""Parse bounded JavaScript/JSX as data. Never evaluate/import generated code.

Syntax validity is separate from file contracts, build validity and isolation.
Diagnostics contain only reviewed filenames and positions, never source text.
"""
from tree_sitter import Language, Parser
import tree_sitter_javascript
import hashlib
import json

PARSER_VERSION = "tree-sitter/0.25.2/javascript/0.25.0"


def save_report(directory, pid, sha, files):
    from agentforge import webapp_builder as base
    base._name(pid, base.PROPOSAL, "proposal id")
    body = {"proposal_id": pid, "source_sha": sha, "syntax": check_files(files, sha)}
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"))
    document = {**body, "report_sha": hashlib.sha256(raw.encode("utf-8")).hexdigest()}
    path = directory / "syntax" / (pid + ".json")
    base._path_guard(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as output:
        json.dump(document, output, indent=2)
    return document


def read_report(directory, pid, sha, files):
    from agentforge import webapp_builder as base
    base._name(pid, base.PROPOSAL, "proposal id")
    path = directory / "syntax" / (pid + ".json")
    base._path_guard(path)
    if not path.is_file() or path.stat().st_size > 24_000:
        raise ValueError("SYNTAX_REPORT_UNAVAILABLE")
    document = json.loads(path.read_text(encoding="utf-8"))
    body = {"proposal_id": pid, "source_sha": sha, "syntax": check_files(files, sha)}
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"))
    expected = {**body, "report_sha": hashlib.sha256(raw.encode("utf-8")).hexdigest()}
    if document != expected:
        raise PermissionError("SYNTAX_REPORT_SOURCE_STALE")
    return document


class SourceSyntaxError(ValueError):
    def __init__(self, report):
        self.report = report
        first = report["diagnostics"][0]
        super().__init__(f"APP_CODE_SYNTAX_INVALID: {first['path']}:{first['line']}:{first['column']} "
                         "invalid JavaScript/JSX; no code executed")


def check_files(files, source_sha):
    # One parser per call: concurrent HTTP/skill execution shares no parser state.
    parser = Parser(Language(tree_sitter_javascript.language()))
    diagnostics = []
    for item in files:
        path, content = item["path"], item["content"]
        if not path.endswith((".js", ".jsx")):
            continue
        raw = content.encode("utf-8")
        if len(raw) > 80_000:
            raise ValueError("APP_CODE_SYNTAX_LIMIT")
        tree = parser.parse(raw)
        pending = [tree.root_node]
        while pending and len(diagnostics) < 8:
            node = pending.pop()
            if node.is_error or node.is_missing:
                diagnostics.append({"path": path, "line": node.start_point.row + 1,
                                    "column": node.start_point.column + 1,
                                    "code": "JSX_SYNTAX_ERROR"})
            elif node.has_error:
                pending.extend(reversed(node.children))
    return {"status": "FAIL" if diagnostics else "PASS", "source_sha": source_sha,
            "stage": "SYNTAX_VALID" if not diagnostics else "SYNTAX_INVALID",
            "parser": PARSER_VERSION, "diagnostics": diagnostics,
            "generated_code_executed": False, "build_verified": False, "browser_verified": False}
