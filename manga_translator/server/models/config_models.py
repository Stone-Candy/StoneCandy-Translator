"""
Configuration data models.
"""

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import List, Optional


@dataclass
class ConfigPreset:
    """Model for configuration presets."""
    
    id: str
    name: str
    description: str
    config: dict
    visible_to_groups: List[str] = field(default_factory=list)
    created_at: Optional[str] = None
    created_by: Optional[str] = None
    updated_at: Optional[str] = None
    
    @classmethod
    def create(cls, name: str, description: str, config: dict,
               created_by: Optional[str] = None,
               visible_to_groups: Optional[List[str]] = None) -> 'ConfigPreset':
        """Create a new ConfigPreset instance."""
        now = datetime.now(timezone.utc).isoformat()
        return cls(
            id=str(uuid.uuid4()),
            name=name,
            description=description,
            config=config,
            visible_to_groups=visible_to_groups or [],
            created_at=now,
            created_by=created_by,
            updated_at=now
        )
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'ConfigPreset':
        """Create instance from dictionary."""
        return cls(**data)
    
    def update(self, **kwargs) -> None:
        """Update preset fields."""
        for key, value in kwargs.items():
            if hasattr(self, key) and key not in ['id', 'created_at', 'created_by']:
                setattr(self, key, value)
        self.updated_at = datetime.now(timezone.utc).isoformat()


@dataclass
class UserConfig:
    """Model for user configurations."""
    
    user_id: str
    api_keys: dict = field(default_factory=dict)
    selected_preset_id: Optional[str] = None
    custom_settings: dict = field(default_factory=dict)
    config_mode: str = "server"  # server or custom
    updated_at: Optional[str] = None
    
    @classmethod
    def create(cls, user_id: str, **kwargs) -> 'UserConfig':
        """Create a new UserConfig instance."""
        return cls(
            user_id=user_id,
            updated_at=datetime.now(timezone.utc).isoformat(),
            **kwargs
        )
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'UserConfig':
        """Create instance from dictionary."""
        return cls(**data)
    
    def update(self, **kwargs) -> None:
        """Update config fields."""
        for key, value in kwargs.items():
            if hasattr(self, key) and key != 'user_id':
                setattr(self, key, value)
        self.updated_at = datetime.now(timezone.utc).isoformat()
