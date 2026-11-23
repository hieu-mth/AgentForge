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
    ("film.tts", "Tạo thoại", "tool", "Local TTS"),
    ("film.assemble", "Dựng video", "tool", "FFmpeg"),
    ("ops.monitor", "Giám sát hệ thống", "tool", "Python rules"),
)
KINDS = {key: kind for key, _, kind, _ in CAPABILITIES}
APPROVALS = ("cloud", "download_or_data_change", "publishing_or_privacy")
TOOLS = ("local_tts", "ffmpeg", "system_rules")


def defaults():
    return {
        "schema_version": 1,
        "primary": None,
        "mode": "SUPERVISED",
        "decompose": False,
        "mappings": {},
        "fallbacks": {},
        "tts_engine": "windows",
        "selection": "FIXED",
        "allowed_profiles": [],
        "fallback": "STOP",
        "gpu_exclusive": True,
        "gpu_concurrency": 1,
        "unavailable": "STOP",
        "retry_limit": 0,
        "retry_unknown_submit": False,
        "reconcile_comfyui": True,
        "permissions": {key: False for key in
                        ("plan", "assign_local", "call_local", "run_tools")},
        "tools": [],
        "approvals": dict.fromkeys(APPROVALS, True),
        "task_budget": 1,
        "paid_api_daily_limit": 10,
    }


def compatible(kind, profile):
    return bool(profile and profile.get("enabled") is True and (
        local_adapter(kind, profile) or
        (kind == "text" and profile.get("provider") == "anthropic")))


def local_adapter(kind, profile):
    """Resolve against the same adapter predicates used by the runtime."""
    from agentforge.features.film_studio import studio_runtime

    resolve = {"text": studio_runtime.text_adapter, "image": studio_runtime.image_adapter,
               "video": studio_runtime.motion_adapter}.get(kind)
    if resolve is None:
        return None
    try:
        return resolve(profile)
    except ValueError:
        return None


def validate(policy, *, id_pattern, extra_routes):
    def require(condition, message):
        if not condition:
            raise ModelConfigError(message)

    default = defaults()
    require(isinstance(policy, dict) and policy.keys() in
            (default.keys(), default.keys() - {"paid_api_daily_limit"}),
            "Cấu trúc chính sách không hợp lệ")
    policy = {"paid_api_daily_limit": default["paid_api_daily_limit"], **policy}
    for key, value in default.items():
        if key != "primary":
            require(type(policy[key]) is type(value), f"Sai kiểu dữ liệu: {key}")
    for key, values in {
        "schema_version": (1,), "mode": ("MANUAL", "SUPERVISED", "AUTOMATIC"),
        "selection": ("FIXED", "SUGGEST"), "fallback": ("STOP", "LOCAL"),
        "unavailable": ("STOP", "WAIT_OWNER"), "tts_engine": ("windows", "piper"),
    }.items():
        require(policy[key] in values, f"Giá trị chưa hỗ trợ: {key}")
    for key, lower, upper in (("gpu_concurrency", 1, 8), ("retry_limit", 0, 5),
                              ("task_budget", 1, 100)):
        require(lower <= policy[key] <= upper, f"Giới hạn không hợp lệ: {key}")
    require(not policy["gpu_exclusive"] or policy["gpu_concurrency"] == 1,
            "GPU độc quyền chỉ cho phép một tác vụ đồng thời")
    require(not policy["retry_unknown_submit"] and policy["reconcile_comfyui"],
            "Phải đối chiếu ComfyUI trước khi chạy lại tác vụ chưa rõ kết quả")
    require(policy["approvals"].keys() == default["approvals"].keys() and
            all(value is True for value in policy["approvals"].values()),
            "Các thao tác nhạy cảm bắt buộc cần Owner duyệt")
    require(policy["permissions"].keys() == default["permissions"].keys() and
            all(type(value) is bool for value in policy["permissions"].values()),
            "Danh sách quyền không hợp lệ")
    def model_id(value):
        return isinstance(value, str) and id_pattern.fullmatch(value) is not None

    require(policy["primary"] is None or model_id(policy["primary"]),
            "Model điều phối không hợp lệ")
    require(policy["mappings"].keys() <= extra_routes and
            all(model_id(value) for value in policy["mappings"].values()),
            "Mapping năng lực không hợp lệ")
    require(policy["fallbacks"].keys() <= {"general.text", "film.storyboard"} and
            all(model_id(value) for value in policy["fallbacks"].values()),
            "Mapping dự phòng không hợp lệ")
    for key, valid, limit in (("allowed_profiles", model_id, 100),
                              ("tools", lambda value: value in TOOLS, len(TOOLS))):
        entries = policy[key]
        require(len(entries) <= limit and
                all(isinstance(value, str) and valid(value) for value in entries) and
                len(set(entries)) == len(entries), f"Danh sách không hợp lệ: {key}")
    require(policy["selection"] != "SUGGEST" or policy["allowed_profiles"],
            "Chọn ít nhất một model được phép đề xuất")
    require(0 <= policy["paid_api_daily_limit"] <= 2**53 - 1,
            "Giới hạn lượt gọi API trả phí phải là số nguyên không âm")
    return policy


def resolve(capability, policy, available_profiles, primary_ref, *, allow_fallback=False):
    """Resolve a configured candidate using an available-profile snapshot."""
    kind = KINDS.get(capability)
    if kind is None:
        return {"status": "UNAVAILABLE", "reason": "UNKNOWN_CAPABILITY",
                "execution_allowed": False}
    if kind == "tool":
        return {"status": ("CONFIG_ONLY" if capability == "film.tts" else "DETERMINISTIC"),
                "tool": policy["tts_engine"] if capability == "film.tts" else
                "ffmpeg" if capability == "film.assemble" else "system_rules",
                "execution_allowed": False}
    primary = available_profiles.get(primary_ref)
    candidates = [ref for ref in policy["allowed_profiles"]
                  if compatible(kind, available_profiles.get(ref))]
    if policy["selection"] == "SUGGEST" and candidates and not allow_fallback:
        return {"status": "CONFIG_ONLY", "candidates": candidates,
                "reason": "OWNER_SELECTION_REQUIRED", "execution_allowed": False}
    if compatible(kind, primary):
        selected, source = primary_ref, "PRIMARY"
    else:
        fallback_ref = policy["fallbacks"].get(capability)
        fallback = available_profiles.get(fallback_ref)
        if (allow_fallback and fallback_ref != primary_ref and policy["fallback"] == "LOCAL" and
                compatible(kind, fallback) and fallback["provider"] == "ollama"):
            selected, source = fallback_ref, "LOCAL_FALLBACK"
        else:
            return {"status": "UNAVAILABLE", "reason": "NO_COMPATIBLE_PROFILE",
                    "execution_allowed": False}
    return {"status": "CONFIG_ONLY", "model_ref": selected, "source": source,
            "requires_owner_approval": available_profiles[selected]["provider"] == "anthropic",
            "execution_allowed": False}
