"""V5 deterministic static QA for a signed AI-generated React source proposal.

No subprocess, browser, model or network. JavaScript/JSX is parsed as data.
PASS_STATIC_ONLY never asserts build,
security or user-flow correctness. Container QA requires a separate Goal.
"""
import hashlib
import json
from uuid import uuid4

from agentforge import webapp_builder as base
from agentforge.features.webapps import architect, developer

REPORTS = base.ROOT / "data" / "company" / "webapp_qa" / "reports"
MAX_REPORT_BYTES = 24_000

def _hash(body):
    raw = json.dumps(body, sort_keys=True, ensure_ascii=False,
                     separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def _path(ident):
    base._name(ident, base.PROPOSAL, "QA report id")
    target = REPORTS / (ident + ".json")
    base._path_guard(target)
    return target

def read(report_id, report_sha):
    if not isinstance(report_sha, str) or not base.SHA.fullmatch(report_sha):
        raise ValueError("QA_INVALID: SHA")
    path = _path(report_id)
    if not path.is_file() or path.stat().st_size > MAX_REPORT_BYTES:
        raise ValueError("QA_INVALID: report unavailable")
    obj = json.loads(path.read_text(encoding="utf-8"))
    required = {"format","qa_report_id","qa_report_sha",
                "architecture_id","architecture_sha","proposal_id","sha256",
                "status","checks","build_verified","browser_verified",
                "security_verified"}
    modern = isinstance(obj, dict) and obj.get("format") == "agentforge.webapp.qa-static.v2"
    if not isinstance(obj,dict) or set(obj) != (required | {"syntax"} if modern else required):
        raise ValueError("QA_INVALID: report fields")
    if (obj["format"] not in {"agentforge.webapp.qa-static.v1", "agentforge.webapp.qa-static.v2"}
            or obj["qa_report_id"] != report_id
            or obj["status"] not in ({"PASS_STATIC_ONLY", "FAIL_SYNTAX"} if modern else {"PASS_STATIC_ONLY"})
            or obj["checks"] != ["SIGNED_ARCHITECTURE","SIGNED_REACT_SOURCE",
                                 "SOURCE_ALLOWLIST","TRUSTED_REACT_TOOLCHAIN"]
            or any(obj[x] is not False for x in (
                "build_verified","browser_verified","security_verified"))):
        raise ValueError("QA_INVALID: report contract")
    for key in ("architecture_sha","sha256"):
        if not isinstance(obj[key],str) or not base.SHA.fullmatch(obj[key]):
            raise ValueError("QA_INVALID: source digest")
    for key in ("architecture_id","proposal_id"):
        base._name(obj[key],base.PROPOSAL,key)
    unsigned = {k:v for k,v in obj.items() if k!="qa_report_sha"}
    if obj["qa_report_sha"] != report_sha or _hash(unsigned) != report_sha:
        raise PermissionError("QA_SOURCE_STALE")
    arch = architect.read(obj["architecture_id"],obj["architecture_sha"])
    app, _ = developer._read_proposal(obj["proposal_id"])
    if (app.get("architecture") != {
            "architecture_id":arch["architecture_id"],
            "architecture_sha":arch["architecture_sha"]}
            or app["sha256"] != obj["sha256"]):
        raise PermissionError("QA_SOURCE_MISMATCH")
    if modern:
        from agentforge.features.webapps.syntax import check_files
        syntax = check_files(app["files"], app["sha256"])
        if (obj["syntax"] != syntax or obj["status"] != (
                "PASS_STATIC_ONLY" if syntax["status"] == "PASS" else "FAIL_SYNTAX")):
            raise ValueError("QA_SYNTAX_MISMATCH")
    return obj

def audit(proposal_id, sha256):
    # _read_proposal statically revalidates all generated paths, import targets,
    # fixed package manifest and checksum; no generated code is executed.
    app, _ = developer._read_proposal(proposal_id)
    if sha256 != app["sha256"]:
        raise PermissionError("QA_SOURCE_STALE")
    lineage = app.get("architecture")
    if not isinstance(lineage,dict):
        raise ValueError("QA_INVALID: V5 requires Architect lineage")
    arch = architect.read(lineage["architecture_id"],lineage["architecture_sha"])
    from agentforge.features.webapps.revisions import _chain
    if arch["project_slug"] != _chain(app)[-1]["project_slug"]:
        raise PermissionError("QA_SOURCE_MISMATCH")
    ident = uuid4().hex
    from agentforge.features.webapps.syntax import check_files
    syntax = check_files(app["files"], sha256)
    status = "PASS_STATIC_ONLY" if syntax["status"] == "PASS" else "FAIL_SYNTAX"
    body = {"format":"agentforge.webapp.qa-static.v2","qa_report_id":ident,
            "architecture_id":lineage["architecture_id"],
            "architecture_sha":lineage["architecture_sha"],
            "proposal_id":proposal_id,"sha256":sha256,
            "status":status, "syntax":syntax,
            "checks":["SIGNED_ARCHITECTURE","SIGNED_REACT_SOURCE",
                      "SOURCE_ALLOWLIST","TRUSTED_REACT_TOOLCHAIN"],
            "build_verified":False,"browser_verified":False,
            "security_verified":False}
    obj = {**body,"qa_report_sha":_hash(body)}
    path = _path(ident)
    path.parent.mkdir(parents=True,exist_ok=True)
    base._path_guard(path)
    with path.open("x",encoding="utf-8") as output:
        json.dump(obj,output,ensure_ascii=False,indent=2)
    return {"qa_report_id":ident, "qa_report_sha":obj["qa_report_sha"],
            "proposal_id":proposal_id, "sha256":sha256,
            "status":status,"build_verified":False,
            "syntax_verified":syntax["status"] == "PASS", "failures":int(syntax["status"] != "PASS"),
            "browser_verified":False,"security_verified":False}
