"""
Data repository classes for JSON file storage.
"""

from manga_translator.server.repositories.base_repository import BaseJSONRepository
from manga_translator.server.repositories.cleanup_repository import CleanupRepository
from manga_translator.server.repositories.config_repository import ConfigRepository
from manga_translator.server.repositories.log_repository import LogRepository
from manga_translator.server.repositories.permission_repository import (
    PermissionRepository,
)
from manga_translator.server.repositories.quota_repository import QuotaRepository
from manga_translator.server.repositories.resource_repository import ResourceRepository
from manga_translator.server.repositories.translation_repository import (
    TranslationRepository,
)

__all__ = [
    'BaseJSONRepository',
    'ResourceRepository',
    'TranslationRepository',
    'PermissionRepository',
    'CleanupRepository',
    'ConfigRepository',
    'QuotaRepository',
    'LogRepository',
]
