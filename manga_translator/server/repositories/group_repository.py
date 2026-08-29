"""
Repository for user group management.
"""

from datetime import datetime, timezone
from typing import Dict, Optional

from manga_translator.server.repositories.base_repository import BaseJSONRepository


class GroupRepository(BaseJSONRepository):
    """Repository for managing user groups."""
    
    # System-defined groups that cannot be deleted or renamed
    SYSTEM_GROUPS = {'admin', 'default', 'guest'}
    
    def _get_default_structure(self):
        """Get default structure for groups file."""
        return {
            "version": "1.0",
            "groups": {
                "admin": {
                    "name": "管理员组",
                    "description": "拥有所有权限的管理员用户组",
                    "parameter_config": {}
                },
                "default": {
                    "name": "默认用户组",
                    "description": "新用户的默认用户组",
                    "parameter_config": {}
                },
                "guest": {
                    "name": "访客组",
                    "description": "受限的访客用户组",
                    "parameter_config": {}
                }
            },
            "last_updated": None
        }
    
    def get_all_groups(self) -> Dict[str, dict]:
        """Get all user groups."""
        data = self._read_data()
        return data.get("groups", {})
    
    def get_group(self, group_id: str) -> Optional[dict]:
        """Get a specific group by ID."""
        data = self._read_data()
        return data.get("groups", {}).get(group_id)
    
    def group_exists(self, group_id: str) -> bool:
        """Check if a group exists."""
        return self.get_group(group_id) is not None
    
    def is_system_group(self, group_id: str) -> bool:
        """Check if a group is a system-defined group."""
        return group_id in self.SYSTEM_GROUPS
    
    def create_group(self, group_id: str, group_data: dict) -> bool:
        """
        Create a new user group.
        
        Args:
            group_id: Unique identifier for the group
            group_data: Group configuration data
        
        Returns:
            True if created successfully, False if group already exists
        """
        data = self._read_data()
        
        if group_id in data.get("groups", {}):
            return False
        
        if "groups" not in data:
            data["groups"] = {}
        
        data["groups"][group_id] = group_data
        self._write_data(data)
        return True
    
    def update_group(self, group_id: str, updates: dict) -> bool:
        """
        Update a group's configuration.
        
        Args:
            group_id: Group identifier
            updates: Dictionary of fields to update
        
        Returns:
            True if updated successfully, False if group doesn't exist
        """
        data = self._read_data()
        
        if group_id not in data.get("groups", {}):
            return False
        
        data["groups"][group_id].update(updates)
        self._write_data(data)
        return True
    
    def rename_group(self, old_id: str, new_id: str, new_name: str) -> bool:
        """
        Rename a user group.
        
        Args:
            old_id: Current group ID
            new_id: New group ID
            new_name: New group name
        
        Returns:
            True if renamed successfully, False otherwise
        """
        if self.is_system_group(old_id):
            return False
        
        data = self._read_data()
        groups = data.get("groups", {})
        
        if old_id not in groups or new_id in groups:
            return False
        
        # Copy group data to new ID
        group_data = groups[old_id].copy()
        group_data["name"] = new_name
        
        # Add new group and remove old one
        groups[new_id] = group_data
        del groups[old_id]
        
        self._write_data(data)
        return True
    
    def delete_group(self, group_id: str) -> bool:
        """
        Delete a user group.
        
        Args:
            group_id: Group identifier
        
        Returns:
            True if deleted successfully, False if group doesn't exist or is system group
        """
        if self.is_system_group(group_id):
            return False
        
        data = self._read_data()
        
        if group_id not in data.get("groups", {}):
            return False
        
        del data["groups"][group_id]
        self._write_data(data)
        return True
    
    def get_group_config(self, group_id: str) -> Optional[dict]:
        """Get the parameter configuration for a group."""
        group = self.get_group(group_id)
        if group:
            return group.get("parameter_config", {})
        return None
    
    def update_group_config(self, group_id: str, config: dict) -> bool:
        """
        Update the configuration for a group.
        
        支持的配置字段：
        - parameter_config: 参数配置
        - allowed_translators: 翻译器白名单
        - denied_translators: 翻译器黑名单
        - default_preset_id: 默认API密钥预设ID
        
        Args:
            group_id: Group identifier
            config: New configuration (可以包含多个字段)
        
        Returns:
            True if updated successfully, False if group doesn't exist
        """
        # 直接使用 update_group 来更新所有传入的字段
        return self.update_group(group_id, config)
    
    def update_last_modified(self) -> None:
        """Update the last_updated timestamp."""
        data = self._read_data()
        data["last_updated"] = datetime.now(timezone.utc).isoformat()
        self._write_data(data)
