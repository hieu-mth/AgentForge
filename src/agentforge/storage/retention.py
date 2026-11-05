"""V3.3 safe local artifact snapshots, verified backups and reversible quarantine.

Never automatically purges user data. Owner-approved quarantine requires a
verified archive, exact live source SHA, and PAUSED operations. Restore is
non-overwriting. SQLite/audit/approval ledgers are not deletion candidates.
"""
import argparse
import hashlib
import json
import os
import re
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from agentforge import ops_control
from agentforge.paths import DATA_DIR, WORKSPACE_DIR, ensure_local_root

WORKSPACE = WORKSPACE_DIR
BACKUPS = DATA_DIR / "backups" / "agentforge"
ID = re.compile(r"[a-f0-9]{32}\Z")
MAX_FILES = 250
MAX_FILE_BYTES = 160 * 1024 * 1024
MAX_TOTAL_BYTES = 350 * 1024 * 1024
READ_CHUNK = 1024 * 1024


def _now():
    return datetime.now(timezone.utc).isoformat()


def _safe(path):
    return ensure_local_root(Path(path))


def _backup_id(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError("Invalid backup ID")
    return value


def _source(kind, name):
    if kind == "website":
        from agentforge import product_builder
        name = product_builder._check_slug(name)
        return _safe(WORKSPACE / "products" / name)
    if kind == "media":
        from agentforge import media_assets
        name = media_assets._run_id(name)
        return _safe(WORKSPACE / "media" / name)
    raise ValueError("Unsupported artifact category")


def _files(root):
    _safe(root)
    if not root.is_dir():
        raise FileNotFoundError("Local artifact not found")
    stack = [root]
    result = []
    total = 0
    while stack:
        folder = stack.pop()
        _safe(folder)
        if not folder.is_dir():
            raise ValueError("Artifact directory changed during scan")
        for entry in sorted(folder.iterdir(), key=lambda x: x.name):
            _safe(entry)
            if entry.is_dir():
                stack.append(entry)
            elif entry.is_file():
                size = entry.stat().st_size
                if size < 0 or size > MAX_FILE_BYTES:
                    raise ValueError("Artifact file exceeds backup limit")
                relative = entry.relative_to(root).as_posix()
                if relative.startswith("/") or any(p in ("", ".", "..") for p in relative.split("/")):
                    raise ValueError("Invalid relative artifact path")
                total += size
                result.append((relative,entry,size))
                if len(result) > MAX_FILES or total > MAX_TOTAL_BYTES:
                    raise ValueError("Artifact backup exceeds bounded file/byte limit")
            else:
                raise ValueError("Unsupported artifact path type")
    if not result:
        raise ValueError("Cannot snapshot an empty artifact")
    return sorted(result, key=lambda x:x[0])


def _file_digest(path, expected):
    digest = hashlib.sha256()
    total = 0
    _safe(path)
    with path.open("rb") as stream:
        while True:
            part = stream.read(READ_CHUNK)
            if not part: break
            total += len(part)
            if total > MAX_FILE_BYTES: raise ValueError("Artifact grew during scan")
            digest.update(part)
    if total != expected:
        raise RuntimeError("Artifact changed while reading")
    return digest.hexdigest()


def _tree_digest(files):
    raw = json.dumps(files, sort_keys=True, ensure_ascii=False,
                     separators=(",",":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def inspect(kind, name):
    root = _source(kind,name)
    files = [{"path":rel,"bytes":size,"sha256":_file_digest(path,size)}
             for rel,path,size in _files(root)]
    return {"kind":kind,"id":name,"tree_sha256":_tree_digest(files),
            "files":files,"file_count":len(files),
            "total_bytes":sum(f["bytes"] for f in files),
            "read_only":True,"source_deleted":False}


def inventory(*, limit=40):
    if type(limit) is not int or not 1 <= limit <= 40:
        raise ValueError("Inventory limit must be 1..40")
    out = []
    for kind,base in (("website",WORKSPACE/"products"),("media",WORKSPACE/"media")):
        _safe(base)
        if not base.exists(): continue
        if not base.is_dir(): raise ValueError("Unexpected artifact root")
        for item in sorted(base.iterdir(),key=lambda x:x.name):
            _safe(item)
            if not item.is_dir(): continue
            try: _source(kind,item.name)
            except (ValueError,PermissionError): continue
            out.append({"kind":kind,"id":item.name,"state":"ACTIVE_LOCAL"})
    return {"items":out[:limit],"total_items":len(out),
            "truncated":len(out)>limit,"read_only":True,
            "automatic_deletion":False}


def _paths(backup_id):
    backup_id = _backup_id(backup_id)
    return (_safe(BACKUPS/(backup_id+".zip")),
            _safe(BACKUPS/(backup_id+".json")))


def _save_receipt(receipt, *, first=False):
    _,target = _paths(receipt["backup_id"])
    _safe(target.parent)
    target.parent.mkdir(parents=True,exist_ok=True)
    tmp = _safe(target.parent/("."+receipt["backup_id"]+"-"+uuid.uuid4().hex+".tmp"))
    payload=json.dumps(receipt,ensure_ascii=False,sort_keys=True,
                       separators=(",",":")).encode("utf-8")
    if len(payload)>65000: raise ValueError("Backup receipt exceeds limit")
    try:
        with tmp.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if first and target.exists():
            raise FileExistsError("Backup receipt already exists")
        os.replace(tmp,target)
    finally:
        if tmp.exists(): tmp.unlink()


def _receipt(backup_id):
    _,path = _paths(backup_id)
    if not path.is_file() or not 0 < path.stat().st_size <= 65000:
        raise FileNotFoundError("Backup receipt missing")
    receipt=json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(receipt,dict) or receipt.get("backup_id")!=backup_id
            or receipt.get("kind") not in ("website","media")
            or receipt.get("status") not in ("BACKED_UP","QUARANTINED","RESTORED")
            or not isinstance(receipt.get("tree_sha256"),str)
            or not ID.fullmatch(receipt.get("quarantine_id","0"*32))):
        raise ValueError("Backup receipt is invalid")
    _source(receipt["kind"],receipt["id"])
    return receipt


def _hash_archive(path):
    digest=hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            chunk=stream.read(READ_CHUNK)
            if not chunk: break
            digest.update(chunk)
    return digest.hexdigest()


def backup(kind,name,tree_sha,*,confirm=False):
    if confirm is not True:
        raise PermissionError("Explicit owner backup confirmation required")
    before=inspect(kind,name)
    if tree_sha!=before["tree_sha256"]:
        raise PermissionError("Artifact SHA changed since inspection")
    backup_id=uuid.uuid4().hex
    archive,_ = _paths(backup_id)
    _safe(archive.parent)
    archive.parent.mkdir(parents=True,exist_ok=True)
    tmp=_safe(archive.parent/("."+backup_id+".zip.tmp"))
    manifests=[]
    try:
        with zipfile.ZipFile(tmp,"x",compression=zipfile.ZIP_STORED,allowZip64=True) as zf:
            for record in before["files"]:
                item=_safe(_source(kind,name)/Path(record["path"]))
                digest=hashlib.sha256()
                count=0
                with item.open("rb") as source, zf.open("files/"+record["path"],"w",
                                                       force_zip64=True) as out:
                    while True:
                        chunk=source.read(READ_CHUNK)
                        if not chunk: break
                        count+=len(chunk)
                        if count>MAX_FILE_BYTES: raise ValueError("Artifact grew")
                        digest.update(chunk)
                        out.write(chunk)
                if count!=record["bytes"] or digest.hexdigest()!=record["sha256"]:
                    raise RuntimeError("Artifact changed while archived")
                manifests.append(record)
            zf.writestr("manifest.json",json.dumps({
                "schema":1,"kind":kind,"id":name,"files":manifests,
                "tree_sha256":tree_sha},sort_keys=True,separators=(",",":")))
        if inspect(kind,name)["tree_sha256"]!=tree_sha:
            raise RuntimeError("Source changed during backup")
        if archive.exists(): raise FileExistsError("Backup ID collision")
        os.replace(tmp,archive)
        archive_sha=_hash_archive(archive)
        receipt={"schema":1,"backup_id":backup_id,"kind":kind,"id":name,
                 "tree_sha256":tree_sha,"archive_sha256":archive_sha,
                 "file_count":len(manifests),"total_bytes":before["total_bytes"],
                 "status":"BACKED_UP","created_at":_now(),
                 "quarantine_id":"0"*32}
        _save_receipt(receipt,first=True)
        verify(backup_id)
        return {"backup_id":backup_id,"status":"BACKED_UP",
                "tree_sha256":tree_sha,"archive_sha256":archive_sha,
                "source_deleted":False,"verified":True}
    finally:
        if tmp.exists(): tmp.unlink()


def verify(backup_id):
    receipt=_receipt(_backup_id(backup_id))
    archive,_=_paths(backup_id)
    _safe(archive)
    if not archive.is_file() or _hash_archive(archive)!=receipt["archive_sha256"]:
        raise PermissionError("Backup archive SHA invalid or archive absent")
    with zipfile.ZipFile(archive,"r") as zf:
        records=json.loads(zf.read("manifest.json"))
        files=records.get("files")
        if (records.get("schema")!=1 or records.get("kind")!=receipt["kind"]
                or records.get("id")!=receipt["id"] or not isinstance(files,list)
                or len(files)>MAX_FILES or
                records.get("tree_sha256")!=receipt["tree_sha256"]
                or _tree_digest(files)!=receipt["tree_sha256"]):
            raise PermissionError("Backup manifest mismatch")
        expected={"files/"+rec["path"] for rec in files}
        if set(zf.namelist())!=expected|{"manifest.json"}:
            raise PermissionError("Backup archive entries mismatch")
        total=0
        for record in files:
            path=record["path"]
            if (not isinstance(path,str) or path.startswith("/")
                    or any(x in ("",".","..") for x in path.split("/"))):
                raise PermissionError("Unsafe backup path")
            info=zf.getinfo("files/"+path)
            if info.file_size!=record["bytes"] or info.file_size>MAX_FILE_BYTES:
                raise PermissionError("Backup file size mismatch")
            digest=hashlib.sha256()
            total+=info.file_size
            if total>MAX_TOTAL_BYTES: raise PermissionError("Backup exceeds size limit")
            with zf.open(info,"r") as stream:
                while True:
                    chunk=stream.read(READ_CHUNK)
                    if not chunk: break
                    digest.update(chunk)
            if digest.hexdigest()!=record["sha256"]:
                raise PermissionError("Backup file SHA mismatch")
    return {"backup_id":backup_id,"status":receipt["status"],
            "kind":receipt["kind"],"id":receipt["id"],
            "tree_sha256":receipt["tree_sha256"],"verified":True,
            "source_deleted":False}


def list_backups(*,limit=40):
    if type(limit) is not int or not 1<=limit<=40:
        raise ValueError("Invalid limit")
    _safe(BACKUPS)
    if not BACKUPS.exists(): return {"items":[],"read_only":True}
    items=[]
    for path in sorted(BACKUPS.glob("*.json")):
        _safe(path)
        if not ID.fullmatch(path.stem): continue
        try:
            row=_receipt(path.stem)
            items.append({k:row[k] for k in ("backup_id","kind","id",
                          "status","tree_sha256","created_at")})
        except (ValueError,FileNotFoundError,KeyError,TypeError,PermissionError):
            continue
    return {"items":items[-limit:],"read_only":True,
            "automatic_deletion":False}


def _require_paused():
    if ops_control.read()["mode"]!="PAUSED":
        raise PermissionError("Pause Operations before changing active artifact location")


def quarantine(backup_id,tree_sha,*,confirm=False):
    if confirm is not True:
        raise PermissionError("Explicit owner quarantine confirmation required")
    _require_paused()
    receipt=_receipt(_backup_id(backup_id))
    if receipt["status"]!="BACKED_UP" or tree_sha!=receipt["tree_sha256"]:
        raise PermissionError("Only exact backed-up artifact may be quarantined")
    verify(backup_id)
    current=inspect(receipt["kind"],receipt["id"])
    if current["tree_sha256"]!=tree_sha:
        raise PermissionError("Source changed since backup")
    folder=_safe(WORKSPACE/".quarantine")
    folder.mkdir(parents=True,exist_ok=True)
    dest=_safe(folder/backup_id)
    if dest.exists(): raise FileExistsError("Quarantine ID collision")
    _source(receipt["kind"],receipt["id"]).rename(dest)
    receipt["status"]="QUARANTINED"
    receipt["quarantine_id"]=backup_id
    receipt["quarantined_at"]=_now()
    _save_receipt(receipt)
    return {"backup_id":backup_id,"status":"QUARANTINED",
            "permanently_deleted":False,"restorable":True}


def restore(backup_id,tree_sha,*,confirm=False):
    if confirm is not True:
        raise PermissionError("Explicit owner restore confirmation required")
    _require_paused()
    receipt=_receipt(_backup_id(backup_id))
    if receipt["status"]!="QUARANTINED" or tree_sha!=receipt["tree_sha256"]:
        raise PermissionError("Only exact quarantined artifact may be restored")
    verify(backup_id)
    old=_safe(WORKSPACE/".quarantine"/backup_id)
    if not old.is_dir() or inspect_folder(old)["tree_sha256"]!=tree_sha:
        raise PermissionError("Quarantined source changed")
    destination=_source(receipt["kind"],receipt["id"])
    if destination.exists(): raise FileExistsError("Original artifact path occupied")
    _safe(destination.parent)
    destination.parent.mkdir(parents=True,exist_ok=True)
    old.rename(destination)
    receipt["status"]="RESTORED"
    receipt["restored_at"]=_now()
    _save_receipt(receipt)
    return {"backup_id":backup_id,"status":"RESTORED",
            "restored":True,"archive_preserved":True}


def inspect_folder(folder):
    files=[{"path":rel,"bytes":size,"sha256":_file_digest(path,size)}
           for rel,path,size in _files(folder)]
    return {"tree_sha256":_tree_digest(files),
            "file_count":len(files),"total_bytes":sum(f["bytes"] for f in files)}


def main():
    parser=argparse.ArgumentParser(description="Owner-gated, reversible artifact retention")
    sub=parser.add_subparsers(dest="action",required=True)
    sub.add_parser("inventory")
    check=sub.add_parser("inspect")
    check.add_argument("kind",choices=["website","media"])
    check.add_argument("id")
    for action in ("backup","quarantine","restore"):
        cmd=sub.add_parser(action)
        if action=="backup":
            cmd.add_argument("kind",choices=["website","media"])
            cmd.add_argument("id")
        else: cmd.add_argument("backup_id")
        cmd.add_argument("--tree-sha",required=True)
        cmd.add_argument("--confirm",action="store_true")
    check=sub.add_parser("verify")
    check.add_argument("backup_id")
    sub.add_parser("backups")
    args=parser.parse_args()
    if args.action=="inventory": result=inventory()
    elif args.action=="inspect": result=inspect(args.kind,args.id)
    elif args.action=="backup": result=backup(args.kind,args.id,args.tree_sha,confirm=args.confirm)
    elif args.action=="quarantine": result=quarantine(args.backup_id,args.tree_sha,confirm=args.confirm)
    elif args.action=="restore": result=restore(args.backup_id,args.tree_sha,confirm=args.confirm)
    elif args.action=="verify": result=verify(args.backup_id)
    else: result=list_backups()
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
