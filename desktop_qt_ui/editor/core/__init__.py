"""编辑器核心模块

此模块包含编辑器的核心数据结构、类型定义和管理器。
"""

from .async_job_manager import AsyncJobManager
from .resource_manager import ResourceManager
from .resources import (
    ImageResource,
    MaskResource,
    RegionResource,
)
from .types import (
    EditorState,
    MaskType,
    ResourceType,
)

__all__ = [
    # Types
    "EditorState",
    "MaskType",
    "ResourceType",
    # Resources
    "ImageResource",
    "MaskResource",
    "RegionResource",
    # Managers
    "AsyncJobManager",
    "ResourceManager",
]

