"""Source-owned composition root; only registered implementations can be resolved.

The Owner database stores profiles and routes, never import paths or executable
adapter code. Catalog discovery does not call external runtimes.
"""
from dataclasses import dataclass
from importlib import import_module
from typing import Any, Callable

from agentforge.ai.orchestrator_policy import ModelConfigError
from agentforge.features.media import flux_workflow
from agentforge.features.film_studio import motion_ltx
from agentforge.integrations import comfy_profile

# These are the profile adapters accepted by Model Hub. Registration is
# configuration only, including for providers with an existing runtime.
ADAPTERS = {
    "ollama": {
        "label": "Ollama", "connection": "local", "model_label": "Tên model",
        "model_example": "qwen3:8b",
        "description": "Model văn bản chạy qua Ollama trên máy này.",
        "defaults": {"base_url": "http://127.0.0.1:11434"}, "local_probe": True,
    },
    "comfyui": {
        "label": "ComfyUI", "connection": "local", "model_label": "Mã checkpoint",
        "model_example": "ltxv-2b-0.9.8-distilled-fp8.safetensors",
        "description": "Hồ sơ ảnh hoặc video. Đăng ký chỉ lưu cấu hình cho ComfyUI.",
        "defaults": {"base_url": "http://127.0.0.1:8188"}, "local_probe": False,
        "flux_workflow_max_bytes": flux_workflow.MAX_WORKFLOW_BYTES,
        "image_workflow_max_bytes": flux_workflow.MAX_WORKFLOW_BYTES,
        "motion_encoder_supported": True,
        "video_workflow_max_bytes": motion_ltx.MAX_CONFIG_BYTES, "media_probe": True,
    },
    "chatgpt": {
        "label": "ChatGPT", "connection": "cloud", "model_label": "Model slug",
        "model_example": "model-tu-lenh-models", "description": "Kết nối local bằng OAuth chính thức; không nhập API key. Chạy CLI chatgpt_auth login trước.",
        "defaults": {"account_ref": "owner"}, "local_probe": False, "cloud_probe": True,
    },
    "openai": {
        "label": "OpenAI API", "connection": "cloud", "model_label": "Model ID",
        "model_example": "model-id-da-cap",
        "description": "API HTTPS tương thích Chat Completions; nhập API base URL và model ID.",
        "defaults": {"base_url": ""},
        "environment_defaults": {"base_url_env": "OPENAI_BASE_URL", "api_key_env": "OPENAI_API_KEY"},
        "local_probe": False, "cloud_probe": True,
    },
    "anthropic": {
        "label": "Anthropic API", "connection": "cloud", "model_label": "Model ID",
        "model_example": "model-id-da-cap",
        "description": "API HTTPS tương thích Anthropic Messages; nhập API base URL và model ID.",
        "defaults": {"base_url": ""},
        "environment_defaults": {"base_url_env": "ANTHROPIC_BASE_URL",
                            "api_key_env": "ANTHROPIC_AUTH_TOKEN"}, "local_probe": False,
        "cloud_probe": True,
    },
    "ltx_cloud": {
        "label": "LTX Video API", "connection": "cloud", "model_label": "Model ID",
        "model_example": "ltx-2-3-fast", "description": "LTX V2 video; 720p, 24 fps, 6/8/10 giây. Chỉ gửi sau duyệt ngân sách.",
        "defaults": {"base_url": "https://api.ltx.io"},
        "environment_defaults": {"base_url_env": "LTX_BASE_URL", "api_key_env": "LTX_API_KEY"},
        "local_probe": False, "cloud_probe": False, "media_probe": True,
    },
    "agnes": {
        "label": "Agnes AI", "connection": "cloud", "model_label": "Model ID",
        "model_example": "agnes-image-2.5-flash",
        "description": "Agnes Image / Video Flash. Kiểm tra hạn mức trước khi tạo nội dung.",
        "defaults": {"base_url": "https://apihub.agnes-ai.com/v1"},
        "environment_defaults": {"base_url_env": "AGNES_BASE_URL", "api_key_env": "AGNES_API_KEY"},
        "local_probe": False, "cloud_probe": False, "media_probe": True,
    },
    "elevenlabs": {
        "label": "ElevenLabs API", "connection": "cloud", "model_label": "Model ID",
        "model_example": "model-id-da-cap",
        "description": "API HTTPS tạo hiệu ứng âm thanh hoặc nhạc; Owner tự chọn model và endpoint.",
        "defaults": {"base_url": ""},
        "environment_defaults": {"base_url_env": "ELEVENLABS_BASE_URL", "api_key_env": "ELEVENLABS_API_KEY"},
        "local_probe": False, "cloud_probe": False,
    },
}


@dataclass(frozen=True)
class ProfileOptions:
    """Registered adapter option sets, independent of credential mode."""
    variants: tuple[frozenset[str], ...] = (frozenset(),)
    validator: Callable | None = None

    @property
    def fields(self):
        return frozenset().union(*self.variants)

    def validate(self, profile, options):
        try:
            validated = self.validator(profile, options) if self.validator else {}
            if not isinstance(validated, dict) or validated.keys() != options.keys():
                raise ModelConfigError("Adapter returned invalid profile options")
            return validated
        except ValueError as exc:
            raise ModelConfigError(str(exc)) from None


def _endpoint_options(path):
    def validate(profile, options):
        if "base_url" in profile:
            import_module(path).validate_endpoint(profile["base_url"])
        return {}
    return ProfileOptions(validator=validate)


PROFILE_OPTIONS = {
    "comfyui": ProfileOptions((frozenset(), frozenset({"flux"}), frozenset({"comfy_image"}), frozenset({"motion_encoder"}), frozenset({"motion_encoder", "comfy_video"})),
                              comfy_profile.validate_settings),
    "ltx_cloud": _endpoint_options("agentforge.features.film_studio.studio_ltx_cloud"),
    "agnes": _endpoint_options("agentforge.features.film_studio.studio_agnes"),
}


def profile_options(provider):
    return PROFILE_OPTIONS.get(provider, ProfileOptions())


@dataclass(frozen=True)
class Registration:
    kind: str
    load: Callable[[], Any]
    providers: tuple[str, ...] = ()
    predicate: str = "supports"

    def matches(self, profile):
        if self.providers:
            return profile.get("provider") in self.providers
        return getattr(self.load(), self.predicate)(profile)


def _module(kind, path, *providers, predicate="supports"):
    return Registration(kind, lambda: import_module(path), providers, predicate)


_STUDIO = "agentforge.features.film_studio."
_MEDIA = "agentforge.features.media."
REGISTRATIONS = (
    _module("text", _STUDIO + "studio_ollama", "ollama"),
    _module("text", _STUDIO + "studio_chatgpt", "chatgpt"),
    _module("text", _STUDIO + "studio_cloud", "openai", "anthropic"),
    _module("image", _MEDIA + "studio_flux"),
    _module("image", _MEDIA + "studio_agnes_image"),
    _module("video", _STUDIO + "draft_motion"),
    _module("video", _STUDIO + "draft_motion_cloud"),
    _module("cloud_video_transport", _STUDIO + "studio_ltx_cloud", predicate="supports_video"),
    _module("cloud_video_transport", _STUDIO + "studio_agnes", predicate="supports_video"),
    _module("vision", _STUDIO + "studio_vision"),
    _module("audio", _STUDIO + "studio_speech"),
    _module("sound", _STUDIO + "studio_audio_generation"),
    _module("music", _STUDIO + "studio_audio_generation"),
)


def resolve(kind, profile):
    """Resolve exactly one implementation; reject unsupported or ambiguous profiles."""
    matches = [entry for entry in REGISTRATIONS
               if entry.kind == kind and profile and entry.matches(profile)]
    if len(matches) != 1:
        raise ValueError("No unique runtime adapter for " + kind)
    return matches[0].load()


def by_id(kind, adapter_id):
    """Resolve persisted artifacts independently of current model assignments."""
    matches = [adapter for entry in REGISTRATIONS if entry.kind == kind
               for adapter in (entry.load(),)
               if getattr(adapter, "ADAPTER_ID", None) == adapter_id]
    if len(matches) != 1:
        raise ValueError("Stored " + kind + " adapter unavailable.")
    return matches[0]
