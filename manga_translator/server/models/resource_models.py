"""
Resource data models for prompts and fonts.
"""

import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass
class PromptResource:
    """Model for user-uploaded prompt resources."""
    
    id: str
    user_id: str
    filename: str
    file_path: str
    file_size: int
    upload_time: str
    file_format: str
    
    @classmethod
    def create(cls, user_id: str, filename: str, file_path: str, 
               file_size: int, file_format: str) -> 'PromptResource':
        """Create a new PromptResource instance."""
        return cls(
            id=str(uuid.uuid4()),
            user_id=user_id,
            filename=filename,
            file_path=file_path,
            file_size=file_size,
            upload_time=datetime.now(timezone.utc).isoformat(),
            file_format=file_format
        )
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'PromptResource':
        """Create instance from dictionary."""
        return cls(**data)


@dataclass
class FontResource:
    """Model for user-uploaded font resources."""
    
    id: str
    user_id: str
    filename: str
    file_path: str
    file_size: int
    upload_time: str
    file_format: str
    font_family: Optional[str] = None
    
    @classmethod
    def create(cls, user_id: str, filename: str, file_path: str, 
               file_size: int, file_format: str, 
               font_family: Optional[str] = None) -> 'FontResource':
        """Create a new FontResource instance."""
        return cls(
            id=str(uuid.uuid4()),
            user_id=user_id,
            filename=filename,
            file_path=file_path,
            file_size=file_size,
            upload_time=datetime.now(timezone.utc).isoformat(),
            file_format=file_format,
            font_family=font_family
        )
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'FontResource':
        """Create instance from dictionary."""
        return cls(**data)
