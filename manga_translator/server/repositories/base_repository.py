"""
Base repository class for JSON file operations with concurrency control.
"""

import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


class BaseJSONRepository:
    """
    Base class for JSON file-based data repositories.
    Provides thread-safe read/write operations and basic query functionality.
    """
    
    def __init__(self, file_path: str):
        """
        Initialize repository with file path.
        
        Args:
            file_path: Path to the JSON file
        """
        self.file_path = file_path
        self._lock = threading.RLock()
        self._ensure_file_exists()
    
    def _ensure_file_exists(self) -> None:
        """Ensure the JSON file and its directory exist."""
        path = Path(self.file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        if not path.exists():
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump(self._get_default_structure(), f, indent=2, ensure_ascii=False)
    
    def _get_default_structure(self) -> Dict[str, Any]:
        """
        Get the default structure for the JSON file.
        Should be overridden by subclasses.
        """
        return {}
    
    def _read_data(self) -> Dict[str, Any]:
        """
        Read data from JSON file with thread safety.
        
        Returns:
            Dictionary containing the file data
        """
        with self._lock:
            try:
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                # If file is corrupted or missing, return default structure
                default = self._get_default_structure()
                self._write_data(default)
                return default
    
    def _write_data(self, data: Dict[str, Any]) -> None:
        """
        Write data to JSON file with thread safety.
        
        Args:
            data: Dictionary to write to file
        """
        with self._lock:
            # Update last_updated timestamp if the structure supports it
            if 'last_updated' in data:
                data['last_updated'] = datetime.now(UTC).isoformat()
            
            # Write to temporary file first, then rename for atomicity
            temp_path = f"{self.file_path}.tmp"
            try:
                with open(temp_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                
                # Atomic rename
                os.replace(temp_path, self.file_path)
            except Exception as e:
                # Clean up temp file if it exists
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                raise e
    
    def query(self, collection_key: str, 
              filter_func: Optional[Callable[[Dict], bool]] = None) -> List[Dict]:
        """
        Query items from a collection with optional filtering.
        
        Args:
            collection_key: Key of the collection in the JSON structure
            filter_func: Optional function to filter items
        
        Returns:
            List of matching items
        """
        data = self._read_data()
        collection = data.get(collection_key, [])
        
        if filter_func is None:
            return collection
        
        return [item for item in collection if filter_func(item)]
    
    def find_by_id(self, collection_key: str, item_id: str) -> Optional[Dict]:
        """
        Find an item by ID in a collection.
        
        Args:
            collection_key: Key of the collection in the JSON structure
            item_id: ID of the item to find
        
        Returns:
            The item if found, None otherwise
        """
        items = self.query(collection_key, lambda x: x.get('id') == item_id)
        return items[0] if items else None
    
    def find_by_field(self, collection_key: str, field: str, 
                      value: Any) -> List[Dict]:
        """
        Find items by a specific field value.
        
        Args:
            collection_key: Key of the collection in the JSON structure
            field: Field name to search
            value: Value to match
        
        Returns:
            List of matching items
        """
        return self.query(collection_key, lambda x: x.get(field) == value)
    
    def add(self, collection_key: str, item: Dict) -> None:
        """
        Add an item to a collection.
        
        Args:
            collection_key: Key of the collection in the JSON structure
            item: Item to add
        """
        data = self._read_data()
        if collection_key not in data:
            data[collection_key] = []
        data[collection_key].append(item)
        self._write_data(data)
    
    def update(self, collection_key: str, item_id: str, 
               updates: Dict) -> bool:
        """
        Update an item in a collection.
        
        Args:
            collection_key: Key of the collection in the JSON structure
            item_id: ID of the item to update
            updates: Dictionary of fields to update
        
        Returns:
            True if item was found and updated, False otherwise
        """
        data = self._read_data()
        collection = data.get(collection_key, [])
        
        for item in collection:
            if item.get('id') == item_id:
                item.update(updates)
                self._write_data(data)
                return True
        
        return False
    
    def delete(self, collection_key: str, item_id: str) -> bool:
        """
        Delete an item from a collection.
        
        Args:
            collection_key: Key of the collection in the JSON structure
            item_id: ID of the item to delete
        
        Returns:
            True if item was found and deleted, False otherwise
        """
        data = self._read_data()
        collection = data.get(collection_key, [])
        
        original_length = len(collection)
        data[collection_key] = [item for item in collection 
                                if item.get('id') != item_id]
        
        if len(data[collection_key]) < original_length:
            self._write_data(data)
            return True
        
        return False
    
    def count(self, collection_key: str, 
              filter_func: Optional[Callable[[Dict], bool]] = None) -> int:
        """
        Count items in a collection with optional filtering.
        
        Args:
            collection_key: Key of the collection in the JSON structure
            filter_func: Optional function to filter items
        
        Returns:
            Count of matching items
        """
        return len(self.query(collection_key, filter_func))
    
    def exists(self, collection_key: str, item_id: str) -> bool:
        """
        Check if an item exists in a collection.
        
        Args:
            collection_key: Key of the collection in the JSON structure
            item_id: ID of the item to check
        
        Returns:
            True if item exists, False otherwise
        """
        return self.find_by_id(collection_key, item_id) is not None
