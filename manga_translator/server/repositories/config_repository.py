"""
Repository for configuration and preset management.
"""

from typing import List, Optional

from manga_translator.server.models import ConfigPreset, UserConfig
from manga_translator.server.repositories.base_repository import BaseJSONRepository


class ConfigRepository(BaseJSONRepository):
    """Repository for managing configuration presets and user configs."""
    
    def _get_default_structure(self):
        """Get default structure for config files."""
        # This will be overridden based on which file is being used
        return {
            "presets": [],
            "last_updated": None
        }
    
    def add_preset(self, preset: ConfigPreset) -> None:
        """Add a configuration preset."""
        self.add("presets", preset.to_dict())
    
    def get_all_presets(self) -> List[dict]:
        """Get all configuration presets."""
        return self.query("presets")
    
    def get_preset_by_id(self, preset_id: str) -> Optional[dict]:
        """Get a preset by its ID."""
        return self.find_by_id("presets", preset_id)
    
    def get_preset_by_name(self, name: str) -> Optional[dict]:
        """Get a preset by its name."""
        presets = self.find_by_field("presets", "name", name)
        return presets[0] if presets else None
    
    def update_preset(self, preset_id: str, updates: dict) -> bool:
        """Update a configuration preset."""
        return self.update("presets", preset_id, updates)
    
    def delete_preset(self, preset_id: str) -> bool:
        """Delete a configuration preset."""
        return self.delete("presets", preset_id)
    
    def get_presets_for_group(self, group_id: str) -> List[dict]:
        """Get presets visible to a specific group."""
        def filter_func(preset):
            visible_groups = preset.get('visible_to_groups', [])
            return not visible_groups or group_id in visible_groups
        
        return self.query("presets", filter_func)


class UserConfigRepository(BaseJSONRepository):
    """Repository for managing user configurations."""
    
    def _get_default_structure(self):
        """Get default structure for user configs file."""
        return {
            "configs": {},
            "last_updated": None
        }
    
    def get_user_config(self, user_id: str) -> Optional[dict]:
        """Get configuration for a specific user."""
        data = self._read_data()
        return data.get("configs", {}).get(user_id)
    
    def set_user_config(self, user_id: str, config: UserConfig) -> None:
        """Set configuration for a specific user."""
        data = self._read_data()
        if "configs" not in data:
            data["configs"] = {}
        data["configs"][user_id] = config.to_dict()
        self._write_data(data)
    
    def delete_user_config(self, user_id: str) -> bool:
        """Delete configuration for a specific user."""
        data = self._read_data()
        if user_id in data.get("configs", {}):
            del data["configs"][user_id]
            self._write_data(data)
            return True
        return False
    
    def update_user_config(self, user_id: str, updates: dict) -> bool:
        """Update configuration for a specific user."""
        data = self._read_data()
        if user_id in data.get("configs", {}):
            data["configs"][user_id].update(updates)
            self._write_data(data)
            return True
        return False
