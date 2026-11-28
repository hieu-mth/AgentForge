"""Owner-only character mutation routes, guarded by server auth/CSRF."""
from agentforge.api.routes._shared import UNHANDLED
from agentforge.features.film_studio import characters, character_references

def handle(server, path, request, session=None):
    if path == "/api/characters/references/save":
        if set(request) != {"ack", "pack"} or request["ack"] != "SAVE_REFERENCE_PACK":
            raise ValueError("Explicit reference pack save acknowledgement required")
        return character_references.save_pack(request["pack"])
    if path == "/api/characters/save":
        if (request.get("ack") != "SAVE_CHARACTER"
                or set(request) - {"ack", "character", "pack"} or "character" not in request):
            raise ValueError("Explicit character save acknowledgement required")
        return character_references.save_character_with_pack(request["character"], request.get("pack"))
    if path == "/api/characters/analyze":
        if session is None or not server.allow_external_actions:
            raise PermissionError("Explicit Owner inference approval required")
        if set(request) != {"ack", "reference", "allow_cloud"} or request["ack"] != "ANALYZE_CHARACTER_PRIMARY":
            raise ValueError("Explicit character analysis acknowledgement required")
        return character_references.analyze_primary(request["reference"], allow_cloud=request["allow_cloud"])
    if path == "/api/characters/archive":
        if set(request) != {"ack", "character_id", "expected_version", "archived"} or request["ack"] != "SET_CHARACTER_ARCHIVED":
            raise ValueError("Explicit character archive acknowledgement required")
        return characters.set_archived(request["character_id"], request["expected_version"], request["archived"])
    return UNHANDLED
