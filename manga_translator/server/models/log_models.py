"""
Log data models.
"""

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class LogEntry:
    """Model for log entries."""
    
    id: str
    session_token: str
    user_id: str
    timestamp: str
    level: str  # info, warning, error
    event_type: str
    message: str
    details: dict = field(default_factory=dict)
    
    @classmethod
    def create(cls, session_token: str, user_id: str, level: str,
               event_type: str, message: str, 
               details: Optional[dict] = None) -> 'LogEntry':
        """Create a new LogEntry instance."""
        return cls(
            id=str(uuid.uuid4()),
            session_token=session_token,
            user_id=user_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            level=level,
            event_type=event_type,
            message=message,
            details=details or {}
        )
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'LogEntry':
        """Create instance from dictionary."""
        return cls(**data)
