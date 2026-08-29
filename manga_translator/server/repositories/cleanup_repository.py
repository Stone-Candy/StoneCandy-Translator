"""
Repository for cleanup rules management.
"""

from typing import List, Optional

from manga_translator.server.models import CleanupRule
from manga_translator.server.repositories.base_repository import BaseJSONRepository


class CleanupRepository(BaseJSONRepository):
    """Repository for managing cleanup rules."""
    
    def _get_default_structure(self):
        """Get default structure for cleanup rules file."""
        return {
            "rules": [],
            "last_updated": None
        }
    
    def add_rule(self, rule: CleanupRule) -> None:
        """Add a cleanup rule."""
        self.add("rules", rule.to_dict())
    
    def get_rule_by_id(self, rule_id: str) -> Optional[dict]:
        """Get a rule by its ID."""
        rules = self.find_by_field("rules", "id", rule_id)
        return rules[0] if rules else None
    
    def get_all_rules(self) -> List[dict]:
        """Get all cleanup rules."""
        return self.query("rules")
    
    def get_enabled_rules(self) -> List[dict]:
        """Get all enabled cleanup rules."""
        return self.query("rules", lambda r: r.get('enabled', True))
    
    def get_rules_by_level(self, level: str) -> List[dict]:
        """Get rules by level (global, user_group, user)."""
        return self.find_by_field("rules", "level", level)
    
    def get_rules_by_target(self, target_id: str) -> List[dict]:
        """Get rules by target ID (user_group_id or user_id)."""
        return self.find_by_field("rules", "target_id", target_id)
    
    def delete_rule(self, rule_id: str) -> bool:
        """Delete a cleanup rule."""
        return self.delete("rules", rule_id)
    
    def update_rule(self, rule_id: str, updates: dict) -> bool:
        """Update a cleanup rule."""
        return self.update("rules", rule_id, updates)
