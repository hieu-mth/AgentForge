"""Versioned Owner policy. Resolution is pure and never authorizes execution."""
class ModelConfigError(ValueError):
    """Invalid model profile, capability binding or Owner policy."""

CAPABILITIES = (
    ("general.text", "Lập kế hoạch", "text", None),
    ("film.storyboard", "Sáng tạo kịch bản", "text", None),
    ("character.select", "Chọn nhân vật", "text", None),
    ("image.generate", "Tạo ảnh", "image", None),
    ("film.motion", "Tạo chuyển động", "video", None),
    ("vision.qa", "Kiểm tra chất lượng hình ảnh", "vision", None),
    ("film.tts", "Tạo thoại cloud", "audio", None),
    ("film.sound", "Sinh hiệu ứng và môi trường", "sound", None),
    ("film.music", "Sinh nhạc nền", "music", None),
    ("film.assemble", "Dựng video", "tool", "FFmpeg"),
    ("ops.monitor", "Giám sát hệ thống", "tool", "Python rules"),
)
KINDS = {key: kind for key, _, kind, _ in CAPABILITIES}
def compatible(kind, profile):
    return bool(profile and profile.get("enabled") is True and (
        runtime_adapter(kind, profile)))


def runtime_adapter(kind, profile):
    """Resolve against the same adapter predicates used by the runtime."""
    from agentforge.features.film_studio import studio_runtime

    if kind in {"sound", "music"}:
        from agentforge.features.film_studio import studio_audio_generation
        return studio_audio_generation if studio_audio_generation.supports(profile) else None
    if kind == "audio":
        from agentforge.features.film_studio import studio_speech
        return studio_speech if studio_speech.supports(profile) else None
    if kind == "vision":
        from agentforge.features.film_studio import studio_vision
        return studio_vision if studio_vision.supports(profile) else None
    resolve = {"text": studio_runtime.text_adapter, "image": studio_runtime.image_adapter,
               "video": studio_runtime.motion_adapter}.get(kind)
    if resolve is None:
        return None
    try:
        return resolve(profile)
    except ValueError:
        return None


def local_adapter(kind, profile):
    if (profile or {}).get("provider") in {"openai", "anthropic", "elevenlabs", "chatgpt", "ltx_cloud"}:
        return None
    return runtime_adapter(kind, profile)


def defaults():
    """Only controls enforced by the current runtime."""
    return {"mode": "SUPERVISED",
            "permissions": dict.fromkeys(("plan", "assign_local", "call_local", "call_cloud", "run_tools"), False),
            "tools": [], "cloud_call_limit": 64}


def validate(policy):
    """Accept only the current execution-policy schema."""
    if not isinstance(policy, dict) or policy.keys() != defaults().keys():
        raise ModelConfigError("Cấu trúc chính sách không hợp lệ")
    if policy["mode"] not in ("MANUAL", "SUPERVISED"):
        raise ModelConfigError("Chế độ thực thi không hợp lệ")
    permissions = policy["permissions"]
    if type(policy["cloud_call_limit"]) is not int or not 1 <= policy["cloud_call_limit"] <= 1000:
        raise ModelConfigError("Ngân sách lượt gọi cloud phải từ 1 đến 1000.")
    if (not isinstance(permissions, dict) or permissions.keys() != defaults()["permissions"].keys()
            or any(type(value) is not bool for value in permissions.values())):
        raise ModelConfigError("Danh sách quyền không hợp lệ")
    if policy["tools"] not in ([], ["ffmpeg"]):
        raise ModelConfigError("Danh sách công cụ không hợp lệ")
    return policy


def resolve(capability, available_profiles, primary_ref):
    """Resolve a configured candidate using an available-profile snapshot."""
    kind = KINDS.get(capability)
    if kind is None:
        return {"status": "UNAVAILABLE", "reason": "UNKNOWN_CAPABILITY",
                "execution_allowed": False}
    if kind == "tool":
        return {"status": "DETERMINISTIC",
                "execution_allowed": False}
    primary = available_profiles.get(primary_ref)
    if not compatible(kind, primary):
        return {"status": "UNAVAILABLE", "reason": "NO_COMPATIBLE_PROFILE",
                "execution_allowed": False}
    selected, source = primary_ref, "PRIMARY"
    return {"status": "CONFIG_ONLY", "model_ref": selected, "source": source,
            "requires_owner_approval": available_profiles[selected]["provider"] in {"openai", "anthropic", "elevenlabs", "chatgpt", "ltx_cloud"},
            "execution_allowed": False}
