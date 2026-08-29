"""
Repository for quota management.
"""

from typing import Dict, Optional

from manga_translator.server.models import QuotaLimit
from manga_translator.server.repositories.base_repository import BaseJSONRepository


class QuotaRepository(BaseJSONRepository):
    """Repository for managing user quotas."""
    
    def _get_default_structure(self):
        """Get default structure for quota file."""
        return {
            "quotas": {},
            "last_updated": None
        }
    
    def get_user_quota(self, user_id: str) -> Optional[dict]:
        """Get quota for a specific user."""
        data = self._read_data()
        return data.get("quotas", {}).get(user_id)
    
    def set_user_quota(self, user_id: str, quota: QuotaLimit) -> None:
        """Set quota for a specific user."""
        data = self._read_data()
        if "quotas" not in data:
            data["quotas"] = {}
        data["quotas"][user_id] = quota.to_dict()
        self._write_data(data)
    
    def update_user_quota(self, user_id: str, updates: dict) -> bool:
        """Update quota for a specific user."""
        data = self._read_data()
        if user_id in data.get("quotas", {}):
            data["quotas"][user_id].update(updates)
            self._write_data(data)
            return True
        return False
    
    def delete_user_quota(self, user_id: str) -> bool:
        """Delete quota for a specific user."""
        data = self._read_data()
        if user_id in data.get("quotas", {}):
            del data["quotas"][user_id]
            self._write_data(data)
            return True
        return False
    
    def get_all_quotas(self) -> Dict[str, dict]:
        """Get all user quotas."""
        data = self._read_data()
        return data.get("quotas", {})
    
    def reset_daily_usage(self, user_id: str) -> bool:
        """Reset daily usage for a specific user."""
        from datetime import UTC, datetime
        return self.update_user_quota(user_id, {
            "current_usage": 0,
            "last_reset": datetime.now(UTC).isoformat()
        })
    
    def increment_usage(self, user_id: str, count: int) -> bool:
        """Increment usage counter for a specific user."""
        data = self._read_data()
        if user_id in data.get("quotas", {}):
            current = data["quotas"][user_id].get("current_usage", 0)
            data["quotas"][user_id]["current_usage"] = current + count
            self._write_data(data)
            return True
        return False
