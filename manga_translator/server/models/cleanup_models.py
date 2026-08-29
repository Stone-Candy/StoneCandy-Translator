"""
Cleanup rule data models.
"""

import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Optional


@dataclass
class CleanupRule:
    """Model for cleanup rules."""
    
    id: str
    level: str  # global, user_group, user
    target_id: Optional[str]  # user_group_id or user_id
    retention_days: int
    enabled: bool = True
    created_at: Optional[str] = None
    created_by: Optional[str] = None
    
    @classmethod
    def create(cls, level: str, retention_days: int, 
               target_id: Optional[str] = None, created_by: Optional[str] = None,
               enabled: bool = True) -> 'CleanupRule':
        """Create a new CleanupRule instance."""
        return cls(
            id=str(uuid.uuid4()),
            level=level,
            target_id=target_id,
            retention_days=retention_days,
            enabled=enabled,
            created_at=datetime.now(UTC).isoformat(),
            created_by=created_by
        )
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'CleanupRule':
        """Create instance from dictionary."""
        return cls(**data)
