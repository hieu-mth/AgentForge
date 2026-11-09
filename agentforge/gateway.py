from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = (ROOT / "workspace").resolve()
MAX_BYTES = 16_384


def safe_path(path: str) -> Path:
    if not isinstance(path, str) or not path.strip():
        raise ValueError("Path must be a non-empty string")

    given = Path(path)

    if given.is_absolute():
        raise PermissionError("Absolute paths are forbidden")

    target = (WORKSPACE / given).resolve()

    if target == WORKSPACE or not target.is_relative_to(WORKSPACE):
        raise PermissionError("Access outside workspace denied")

    return target


def read_file(path: str) -> str:
    target = safe_path(path)

    if target.stat().st_size > MAX_BYTES:
        raise ValueError("File exceeds size limit")

    return target.read_text(encoding="utf-8")


def write_file(path: str, content: str) -> dict:
    if not isinstance(content, str):
        raise ValueError("Content must be text")

    if len(content.encode("utf-8")) > MAX_BYTES:
        raise ValueError("Content exceeds size limit")

    target = safe_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    try:
        with target.open("x", encoding="utf-8") as file:
            file.write(content)

        return {"status": "created", "path": path}

    except FileExistsError:
        existing = read_file(path)

        if existing != content:
            raise RuntimeError(
                "File exists with different content"
            )

        return {
            "status": "already_exists_same_content",
            "path": path
        }


TOOLS = {
    "read_file": read_file,
    "write_file": write_file,
}


def execute_tool(name: str, arguments: dict):
    if name not in TOOLS:
        raise PermissionError(f"Tool not authorized: {name}")

    if not isinstance(arguments, dict):
        raise ValueError("Arguments must be a dictionary")

    return TOOLS[name](**arguments)
