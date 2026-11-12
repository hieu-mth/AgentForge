"""Owner-only character mutation routes, guarded by server auth/CSRF."""
from agentforge.api.routes._shared import UNHANDLED
from agentforge.features.film_studio.characters import save_character

def handle(server, path, request, session=None):
    if path == "/api/characters/save":
        if request.get("ack") != "SAVE_CHARACTER":
            raise ValueError("Explicit character save acknowledgement required")
        return {"character": save_character(request.get("character"))}
    return UNHANDLED
