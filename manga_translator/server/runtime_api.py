from typing import Optional

RUNTIME_API_ENV_PRIORITY = {
    "translator": {
        "sakura": {
            "api_base": ["SAKURA_API_BASE"],
        },
    },
    "ocr": {
        "openai": {
            "api_key": ["OCR_OPENAI_API_KEY"],
            "api_base": ["OCR_OPENAI_API_BASE"],
            "model": ["OCR_OPENAI_MODEL"],
        },
        "gemini": {
            "api_key": ["OCR_GEMINI_API_KEY"],
            "api_base": ["OCR_GEMINI_API_BASE"],
            "model": ["OCR_GEMINI_MODEL"],
        },
    },
    "colorizer": {
        "openai": {
            "api_key": ["COLOR_OPENAI_API_KEY"],
            "api_base": ["COLOR_OPENAI_API_BASE"],
            "model": ["COLOR_OPENAI_MODEL"],
        },
        "gemini": {
            "api_key": ["COLOR_GEMINI_API_KEY"],
            "api_base": ["COLOR_GEMINI_API_BASE"],
            "model": ["COLOR_GEMINI_MODEL"],
        },
    },
    "renderer": {
        "openai": {
            "api_key": ["RENDER_OPENAI_API_KEY"],
            "api_base": ["RENDER_OPENAI_API_BASE"],
            "model": ["RENDER_OPENAI_MODEL"],
        },
        "gemini": {
            "api_key": ["RENDER_GEMINI_API_KEY"],
            "api_base": ["RENDER_GEMINI_API_BASE"],
            "model": ["RENDER_GEMINI_MODEL"],
        },
    },
}


def _pick_first_env(env_vars: dict, candidates: list[str]) -> Optional[str]:
    for key in candidates:
        value = env_vars.get(key)
        if value:
            return str(value)
    return None


def build_runtime_api_overrides(env_vars: Optional[dict]) -> dict[str, dict[str, dict[str, str]]]:
    env_vars = {
        str(key): str(value)
        for key, value in (env_vars or {}).items()
        if key and value
    }
    overrides: dict[str, dict[str, dict[str, str]]] = {}
    for feature, providers in RUNTIME_API_ENV_PRIORITY.items():
        feature_overrides: dict[str, dict[str, str]] = {}
        for provider, field_map in providers.items():
            provider_overrides = {
                field_name: value
                for field_name, candidates in field_map.items()
                if (value := _pick_first_env(env_vars, candidates))
            }
            if provider_overrides:
                feature_overrides[provider] = provider_overrides
        if feature_overrides:
            overrides[feature] = feature_overrides
    return overrides


def apply_runtime_api_overrides(config, env_vars: Optional[dict]) -> None:
    if config is None:
        return
    config._runtime_api_overrides = build_runtime_api_overrides(env_vars)


def clear_runtime_api_overrides(config) -> None:
    if config is None:
        return
    config._runtime_api_overrides = {}
