"""Model profiles: stable logical IDs, no credentials stored in TOML."""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config" / "models.toml"
ENV_NAME = re.compile(r"[A-Z_][A-Z0-9_]*\Z")


class ModelConfigError(ValueError):
    pass


def load_models(path=None):
    config_path = Path(path) if path is not None else DEFAULT_CONFIG
    if not config_path.is_file():
        raise ModelConfigError(f"Model configuration not found: {config_path}")

    try:
        content = config_path.read_text(encoding="utf-8-sig")
        config = tomllib.loads(content)
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ModelConfigError("Cannot read model configuration") from exc

    models = config.get("models")
    if not isinstance(models, dict) or not models:
        raise ModelConfigError("Model registry must not be empty")

    for model_id, entry in models.items():
        if not isinstance(entry, dict):
            raise ModelConfigError(f"Invalid model: {model_id}")

        if any(key in entry for key in ("api_key", "token", "password", "secret")):
            raise ModelConfigError(f"Plaintext credentials forbidden: {model_id}")

        provider = entry.get("provider")
        model_name = entry.get("model")
        if provider not in ("ollama", "anthropic"):
            raise ModelConfigError(f"Unsupported provider: {model_id}")
        if not isinstance(model_name, str) or not model_name.strip():
            raise ModelConfigError(f"Missing model name: {model_id}")
        if type(entry.get("enabled")) is not bool:
            raise ModelConfigError(f"Invalid enabled flag: {model_id}")

        if provider == "ollama":
            url = entry.get("base_url")
            if not isinstance(url, str) or not url.strip():
                raise ModelConfigError(f"Missing Ollama endpoint: {model_id}")
        else:
            # Cloud endpoints/credentials live in .env or process env only.
            if "base_url" in entry:
                raise ModelConfigError(f"Cloud URL must use base_url_env: {model_id}")
            for name in ("base_url_env", "api_key_env"):
                value = entry.get(name)
                if not isinstance(value, str) or not ENV_NAME.fullmatch(value):
                    raise ModelConfigError(f"Invalid {name}: {model_id}")

    return models
