"""
Repository for user resource management (prompts and fonts).
"""

from typing import List, Optional

from manga_translator.server.models.resource_models import FontResource, PromptResource
from manga_translator.server.repositories.base_repository import BaseJSONRepository


class ResourceRepository(BaseJSONRepository):
    """Repository for managing user resources."""
    
    def _get_default_structure(self):
        """Get default structure for resource index files."""
        return {
            "resources": [],
            "last_updated": None
        }
    
    def add_resource(self, resource: PromptResource | FontResource) -> None:
        """Add a resource to the index."""
        self.add("resources", resource.to_dict())
    
    def get_user_resources(self, user_id: str) -> List[dict]:
        """Get all resources for a specific user."""
        return self.find_by_field("resources", "user_id", user_id)
    
    def get_resource_by_id(self, resource_id: str) -> Optional[dict]:
        """Get a resource by its ID."""
        return self.find_by_id("resources", resource_id)
    
    def delete_resource(self, resource_id: str) -> bool:
        """Delete a resource from the index."""
        return self.delete("resources", resource_id)
    
    def update_resource(self, resource_id: str, updates: dict) -> bool:
        """Update a resource in the index."""
        return self.update("resources", resource_id, updates)
