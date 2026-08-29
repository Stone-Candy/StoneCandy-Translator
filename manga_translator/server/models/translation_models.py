"""
Translation result data models.
"""

import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass
class TranslationResult:
    """Model for translation results."""
    
    id: str
    user_id: str
    session_token: str
    timestamp: str
    file_count: int
    total_size: int
    result_path: str
    metadata: dict
    status: str = "completed"
    
    @classmethod
    def create(cls, user_id: str, session_token: str, file_count: int,
               total_size: int, result_path: str, metadata: Optional[dict] = None,
               status: str = "completed") -> 'TranslationResult':
        """Create a new TranslationResult instance."""
        return cls(
            id=str(uuid.uuid4()),
            user_id=user_id,
            session_token=session_token,
            timestamp=datetime.now(timezone.utc).isoformat(),
            file_count=file_count,
            total_size=total_size,
            result_path=result_path,
            metadata=metadata or {},
            status=status
        )
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'TranslationResult':
        """Create instance from dictionary."""
        return cls(**data)
