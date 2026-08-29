"""
Quota data models.
"""

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Optional


@dataclass
class QuotaLimit:
    """Model for user quota limits."""
    
    user_id: str
    max_file_size: int = 10485760  # 10MB default
    max_files_per_upload: int = 10
    max_sessions: int = 5
    daily_quota: int = -1  # -1 means unlimited
    current_usage: int = 0
    last_reset: Optional[str] = None
    
    @classmethod
    def create(cls, user_id: str, **limits) -> 'QuotaLimit':
        """Create a new QuotaLimit instance."""
        return cls(
            user_id=user_id,
            last_reset=datetime.now(UTC).isoformat(),
            **limits
        )
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'QuotaLimit':
        """Create instance from dictionary."""
        return cls(**data)
    
    def reset_daily_usage(self) -> None:
        """Reset daily usage counter."""
        self.current_usage = 0
        self.last_reset = datetime.now(UTC).isoformat()
    
    def increment_usage(self, count: int) -> None:
        """Increment usage counter."""
        self.current_usage += count


@dataclass
class QuotaStats:
    """Model for quota statistics."""
    
    user_id: str
    daily_limit: int
    used_today: int
    remaining: int
    active_sessions: int
    total_uploaded: int
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'QuotaStats':
        """Create instance from dictionary."""
        return cls(**data)
