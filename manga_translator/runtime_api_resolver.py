import os
from dataclasses import dataclass
from typing import Optional

from .api_key_rotation import (
    APIEndpoint,
    get_indexed_env_key,
    get_rotation_slot_count,
    get_strategy_env_key,
    make_endpoint_status_key,
    normalize_rotation_strategy,
)
from .utils.openai_compat import resolve_openai_compatible_api_key


@dataclass(frozen=True)
class RuntimeAPIConfig:
    api_key: Optional[str]
    base_url: str
    model_name: str
    candidates: tuple[APIEndpoint, ...] = ()
    strategy: str = "failover"


def get_runtime_api_override(config, feature: str, provider: str) -> dict[str, str]:
    if config is None:
        return {}
    overrides = getattr(config, "_runtime_api_overrides", None) or {}
    return dict(overrides.get(feature, {}).get(provider, {}))


def _read_env(env_key: Optional[str], index: int = 1) -> Optional[str]:
    indexed_key = get_indexed_env_key(env_key, index)
    if not indexed_key:
        return None
    value = os.getenv(indexed_key)
    return value if value is not None else None


def _normalize_api_key(api_key: Optional[str], base_url: str, allow_empty_local_api_key: bool) -> Optional[str]:
    if allow_empty_local_api_key:
        return resolve_openai_compatible_api_key(api_key, base_url)
    return api_key


def _build_endpoint(
    *,
    feature: str,
    provider: str,
    index: int,
    api_key: Optional[str],
    base_url: str,
    model_name: str,
    allow_empty_local_api_key: bool,
) -> APIEndpoint | None:
    resolved_api_key = _normalize_api_key(api_key, base_url, allow_empty_local_api_key)
    if not str(resolved_api_key or "").strip():
        return None
    base_url = (base_url or "").rstrip("/")
    status_key = make_endpoint_status_key(
        feature,
        provider,
        index,
        base_url,
        model_name,
        api_key=resolved_api_key,
    )
    return APIEndpoint(
        feature=feature,
        provider=provider,
        slot=index,
        api_key=resolved_api_key,
        base_url=base_url,
        model_name=model_name,
        status_key=status_key,
        label=f"{provider} #{index}",
    )


def resolve_runtime_api_config(
    config,
    *,
    feature: str,
    provider: str,
    api_key_env: Optional[str],
    api_base_env: Optional[str],
    model_env: Optional[str],
    fallback_api_key_env: Optional[str],
    fallback_api_base_env: Optional[str],
    fallback_model_env: Optional[str],
    default_api_base: str,
    default_model: str,
    allow_empty_local_api_key: bool = False,
) -> RuntimeAPIConfig:
    override = get_runtime_api_override(config, feature, provider)
    allow_server_api_keys = getattr(config, "_allow_server_api_keys", True)
    override_api_key = override.get("api_key")
    override_base_url = override.get("api_base")
    override_model_name = override.get("model")

    if override_api_key or override_base_url or override_model_name:
        base_url = (
            override_base_url
            or (os.getenv(api_base_env) if api_base_env else None)
            or (os.getenv(fallback_api_base_env) if fallback_api_base_env else None)
            or default_api_base
        )
        model_name = (
            override_model_name
            or (os.getenv(model_env) if model_env else None)
            or (os.getenv(fallback_model_env) if fallback_model_env else None)
            or default_model
        )
        api_key = override_api_key or (
            (
                os.getenv(api_key_env)
                if allow_server_api_keys and api_key_env
                else None
            )
            or (
                os.getenv(fallback_api_key_env)
                if allow_server_api_keys and fallback_api_key_env
                else None
            )
        )
        api_key = _normalize_api_key(api_key, base_url, allow_empty_local_api_key)
        endpoint = _build_endpoint(
            feature=feature,
            provider=provider,
            index=1,
            api_key=api_key,
            base_url=base_url,
            model_name=model_name,
            allow_empty_local_api_key=False,
        )
        candidates = (endpoint,) if endpoint else ()
        return RuntimeAPIConfig(
            api_key=api_key,
            base_url=(base_url or default_api_base).rstrip("/"),
            model_name=model_name or default_model,
            candidates=candidates,
            strategy="failover",
        )

    strategy_key = get_strategy_env_key(api_key_env)
    strategy = normalize_rotation_strategy(os.getenv(strategy_key) if strategy_key else None)
    slot_count = get_rotation_slot_count(
        dict(os.environ),
        (api_key_env, api_base_env, model_env, fallback_api_key_env, fallback_api_base_env, fallback_model_env),
    )

    candidates: list[APIEndpoint] = []
    seen: set[tuple[str, str, str]] = set()
    for index in range(1, slot_count + 1):
        api_key = (
            _read_env(api_key_env, index)
            if allow_server_api_keys and api_key_env
            else None
        ) or (
            _read_env(fallback_api_key_env, index)
            if allow_server_api_keys and fallback_api_key_env
            else None
        )
        base_url = (
            _read_env(api_base_env, index)
            if api_base_env
            else None
        ) or (
            _read_env(fallback_api_base_env, index)
            if fallback_api_base_env
            else None
        ) or default_api_base
        model_name = (
            _read_env(model_env, index)
            if model_env
            else None
        ) or (
            _read_env(fallback_model_env, index)
            if fallback_model_env
            else None
        ) or default_model
        endpoint = _build_endpoint(
            feature=feature,
            provider=provider,
            index=index,
            api_key=api_key,
            base_url=base_url,
            model_name=model_name,
            allow_empty_local_api_key=allow_empty_local_api_key,
        )
        if endpoint is None:
            continue
        dedupe_key = (endpoint.api_key or "", endpoint.base_url, endpoint.model_name)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        candidates.append(endpoint)

    if candidates:
        primary = candidates[0]
        api_key = primary.api_key
        base_url = primary.base_url
        model_name = primary.model_name
    else:
        api_key = None
        base_url = (
            (os.getenv(api_base_env) if api_base_env else None)
            or (os.getenv(fallback_api_base_env) if fallback_api_base_env else None)
            or default_api_base
        )
        model_name = (
            (os.getenv(model_env) if model_env else None)
            or (os.getenv(fallback_model_env) if fallback_model_env else None)
            or default_model
        )
    return RuntimeAPIConfig(
        api_key=api_key,
        base_url=(base_url or default_api_base).rstrip("/"),
        model_name=model_name or default_model,
        candidates=tuple(candidates),
        strategy=strategy,
    )
