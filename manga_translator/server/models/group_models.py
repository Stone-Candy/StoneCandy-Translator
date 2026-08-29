"""
User group data models.
"""

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import List, Optional


@dataclass
class UserGroup:
    """Model for user groups."""
    
    id: str
    name: str
    description: str
    permissions: dict = field(default_factory=dict)
    quota_limits: dict = field(default_factory=dict)
    visible_presets: List[str] = field(default_factory=list)
    created_at: Optional[str] = None
    created_by: Optional[str] = None
    is_system: bool = False
    
    @classmethod
    def create(cls, name: str, description: str, 
               created_by: Optional[str] = None,
               is_system: bool = False,
               permissions: Optional[dict] = None,
               quota_limits: Optional[dict] = None,
               visible_presets: Optional[List[str]] = None) -> 'UserGroup':
        """Create a new UserGroup instance."""
        return cls(
            id=str(uuid.uuid4()),
            name=name,
            description=description,
            permissions=permissions or {},
            quota_limits=quota_limits or {},
            visible_presets=visible_presets or [],
            created_at=datetime.now(timezone.utc).isoformat(),
            created_by=created_by,
            is_system=is_system
        )
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'UserGroup':
        """Create instance from dictionary."""
        return cls(**data)
    
    def update(self, **kwargs) -> None:
        """Update group fields."""
        for key, value in kwargs.items():
            if hasattr(self, key) and key not in ['id', 'created_at', 'created_by', 'is_system']:
                setattr(self, key, value)
