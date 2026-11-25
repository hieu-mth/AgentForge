"""Owner-only character mutation routes, guarded by server auth/CSRF."""
from agentforge.api.routes._shared import UNHANDLED
from agentforge.features.film_studio.characters import save_character

def handle(server, path, request, session=None):
    if path == "/api/characters/references/save":
        if set(request) != {"ack", "pack"} or request["ack"] != "SAVE_REFERENCE_PACK":
            raise ValueError("Explicit reference pack save acknowledgement required")
        from agentforge.features.film_studio import character_references
        return character_references.save_pack(request["pack"])
    if path == "/api/characters/save":
        if request.get("ack") != "SAVE_CHARACTER":
            raise ValueError("Explicit character save acknowledgement required")
        return {"character": save_character(request.get("character"))}
    return UNHANDLED
