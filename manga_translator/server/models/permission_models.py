"""
Permission data models.
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass
class UserPermission:
    """Model for user permissions."""
    
    user_id: str
    can_upload_prompt: bool = False
    can_upload_font: bool = False
    view_permission: str = "own"  # own, none, all
    save_enabled: bool = True
    can_delete_own_files: bool = True
    can_delete_all_files: bool = False
    can_edit_own_env: bool = False
    can_edit_server_env: bool = False
    can_view_own_logs: bool = True
    can_view_all_logs: bool = False
    can_view_system_logs: bool = False
    updated_at: Optional[str] = None
    updated_by: Optional[str] = None
    
    @classmethod
    def create(cls, user_id: str, updated_by: Optional[str] = None, 
               **permissions) -> 'UserPermission':
        """Create a new UserPermission instance."""
        return cls(
            user_id=user_id,
            updated_at=datetime.now(timezone.utc).isoformat(),
            updated_by=updated_by,
            **permissions
        )
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'UserPermission':
        """Create instance from dictionary."""
        return cls(**data)
    
    def update(self, updated_by: str, **permissions) -> None:
        """Update permissions."""
        for key, value in permissions.items():
            if hasattr(self, key):
                setattr(self, key, value)
        self.updated_at = datetime.now(timezone.utc).isoformat()
        self.updated_by = updated_by
