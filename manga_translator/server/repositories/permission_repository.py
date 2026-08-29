"""
Repository for permission management.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from manga_translator.server.models import UserPermission
from manga_translator.server.repositories.base_repository import BaseJSONRepository


class PermissionRepository(BaseJSONRepository):
    """Repository for managing user and group permissions."""
    
    def _get_default_structure(self):
        """Get default structure for permissions file."""
        return {
            "global_permissions": {
                "can_upload_prompt": False,
                "can_upload_font": False,
                "can_delete_own_files": True,
                "can_delete_all_files": False,
                "view_permission": "own",
                "save_enabled": True,
                "can_edit_own_env": False,
                "can_edit_server_env": False,
                "can_view_own_logs": True,
                "can_view_all_logs": False,
                "can_view_system_logs": False
            },
            "group_permissions": {},
            "user_permissions": {},
            "last_updated": None
        }
    
    def get_global_permissions(self) -> dict:
        """Get global default permissions."""
        data = self._read_data()
        return data.get("global_permissions", {})
    
    def set_global_permissions(self, permissions: dict) -> None:
        """Set global default permissions."""
        data = self._read_data()
        data["global_permissions"].update(permissions)
        self._write_data(data)
    
    def get_group_permissions(self, group_id: str) -> Optional[dict]:
        """Get permissions for a specific group."""
        data = self._read_data()
        return data.get("group_permissions", {}).get(group_id)
    
    def set_group_permissions(self, group_id: str, permissions: dict) -> None:
        """Set permissions for a specific group."""
        data = self._read_data()
        if "group_permissions" not in data:
            data["group_permissions"] = {}
        data["group_permissions"][group_id] = permissions
        self._write_data(data)
    
    def get_user_permissions(self, user_id: str) -> Optional[dict]:
        """Get permissions for a specific user."""
        data = self._read_data()
        return data.get("user_permissions", {}).get(user_id)
    
    def set_user_permissions(self, user_id: str, permissions: UserPermission) -> None:
        """Set permissions for a specific user."""
        data = self._read_data()
        if "user_permissions" not in data:
            data["user_permissions"] = {}
        
        # Convert to dict and remove fields with None values to support partial updates
        perm_dict = permissions.to_dict()
        # Keep metadata fields even if None
        filtered_dict = {
            k: v for k, v in perm_dict.items()
            if v is not None or k in ['user_id', 'updated_at', 'updated_by']
        }
        
        data["user_permissions"][user_id] = filtered_dict
        self._write_data(data)
    
    def delete_user_permissions(self, user_id: str) -> bool:
        """Delete permissions for a specific user."""
        data = self._read_data()
        if user_id in data.get("user_permissions", {}):
            del data["user_permissions"][user_id]
            self._write_data(data)
            return True
        return False
    
    def delete_group_permissions(self, group_id: str) -> bool:
        """Delete permissions for a specific group."""
        data = self._read_data()
        if group_id in data.get("group_permissions", {}):
            del data["group_permissions"][group_id]
            self._write_data(data)
            return True
        return False
    
    def get_effective_permissions(self, user_id: str, group_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get effective permissions for a user with inheritance.
        
        Inheritance order: global → group → user
        User-level permissions override group-level, which override global.
        Only non-None values from higher priority levels override lower priority levels.
        
        Args:
            user_id: User ID
            group_id: Optional group ID for the user
        
        Returns:
            Dictionary of effective permissions
        """
        data = self._read_data()
        
        # Start with global permissions
        effective = data.get("global_permissions", {}).copy()
        
        # Apply group permissions if group_id is provided
        if group_id:
            group_perms = data.get("group_permissions", {}).get(group_id, {})
            # Only update fields that are explicitly set in group permissions
            for key, value in group_perms.items():
                if value is not None:
                    effective[key] = value
        
        # Apply user-specific permissions (highest priority)
        user_perms = data.get("user_permissions", {}).get(user_id, {})
        if user_perms:
            # Remove metadata fields and only apply explicitly set permissions
            for key, value in user_perms.items():
                if key not in ['user_id', 'updated_at', 'updated_by'] and value is not None:
                    effective[key] = value
        
        return effective
    
    def update_last_modified(self) -> None:
        """Update the last_updated timestamp."""
        data = self._read_data()
        data["last_updated"] = datetime.now(timezone.utc).isoformat()
        self._write_data(data)
