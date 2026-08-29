from typing import Optional

from manga_translator.server.core.group_management_service import (
    get_group_management_service,
)
from manga_translator.server.core.middleware import get_services

DEFAULT_API_KEY_POLICY = {
    "require_user_keys": False,
    "allow_server_keys": True,
    "save_user_keys_to_server": False,
    "show_env_editor": False,
}

GROUP_POLICY_KEYS = (
    "require_user_keys",
    "allow_server_keys",
    "save_user_keys_to_server",
    "show_env_editor",
)


def get_global_api_key_policy(admin_settings: Optional[dict] = None) -> dict:
    settings = admin_settings or {}
    policy = dict(DEFAULT_API_KEY_POLICY)
    policy.update(settings.get("api_key_policy", {}))
    policy["show_env_editor"] = settings.get(
        "show_env_to_users",
        policy["show_env_editor"],
    )
    return policy


def get_group_api_key_policy(username: Optional[str]) -> dict:
    if not username:
        return {}

    try:
        account_service, _, _ = get_services()
        account = account_service.get_user(username)
        if not account:
            return {}

        group = get_group_management_service().get_group(account.group)
        if not group:
            return {}

        parameter_config = group.get("parameter_config", {}) or {}
        group_permissions = parameter_config.get("permissions", {}) or {}
        if not isinstance(group_permissions, dict):
            return {}

        return {
            key: group_permissions[key]
            for key in GROUP_POLICY_KEYS
            if key in group_permissions
        }
    except Exception:
        return {}


def get_effective_api_key_policy(
    username: Optional[str],
    admin_settings: Optional[dict] = None,
) -> dict:
    policy = get_global_api_key_policy(admin_settings)
    policy.update(get_group_api_key_policy(username))
    return policy
