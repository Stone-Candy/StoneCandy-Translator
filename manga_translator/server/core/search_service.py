"""
Search Service for translation history.

This service provides:
- Fuzzy filename search
- Date range search
- Session token search
- Combined search with multiple filters
"""

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from manga_translator.server.models import TranslationResult
from manga_translator.server.repositories.translation_repository import (
    TranslationRepository,
)

logger = logging.getLogger(__name__)


class SearchService:
    """
    Service for searching translation history.
    
    Validates: Requirements 13.1-13.5
    """
    
    def __init__(self, translation_repo: Optional[TranslationRepository] = None):
        """
        Initialize the search service.
        
        Args:
            translation_repo: Optional translation repository instance
        """
        self.translation_repo = translation_repo or TranslationRepository(
            'manga_translator/server/data/translation_history.json'
        )
    
    def search(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None
    ) -> List[TranslationResult]:
        """
        Search translation history with query and filters.
        
        Args:
            query: Search query string
            filters: Optional filters (start_date, end_date, status)
            user_id: Optional user ID to limit search scope
        
        Returns:
            List of matching TranslationResult objects
            
        Validates: Requirement 13.1
        """
        filters = filters or {}
        
        # Get base sessions
        sessions = self.translation_repo.search_sessions(
            user_id=user_id,
            start_date=filters.get('start_date'),
            end_date=filters.get('end_date')
        )
        
        # Apply status filter
        if 'status' in filters:
            sessions = [s for s in sessions if s.get('status') == filters['status']]
        
        # Apply query filter
        if query:
            sessions = self._filter_by_query(sessions, query)
        
        # Convert to TranslationResult objects
        results = [TranslationResult.from_dict(s) for s in sessions]
        
        # Sort by relevance (for now, just by timestamp)
        results.sort(key=lambda x: x.timestamp, reverse=True)
        
        return results
    
    def fuzzy_search_filename(
        self,
        query: str,
        user_id: Optional[str] = None
    ) -> List[TranslationResult]:
        """
        Fuzzy search by filename.
        
        Args:
            query: Filename query (supports partial matching)
            user_id: Optional user ID to limit search scope
        
        Returns:
            List of matching TranslationResult objects
            
        Validates: Requirement 13.4
        """
        # Get all sessions for user
        sessions = self.translation_repo.search_sessions(user_id=user_id)
        
        # Filter by filename
        query_lower = query.lower()
        matching_sessions = []
        
        for session in sessions:
            metadata = session.get('metadata', {})
            files = metadata.get('files', [])
            
            # Check if any file matches the query
            for filename in files:
                if query_lower in filename.lower():
                    matching_sessions.append(session)
                    break
        
        # Convert to TranslationResult objects
        results = [TranslationResult.from_dict(s) for s in matching_sessions]
        
        # Sort by timestamp (newest first)
        results.sort(key=lambda x: x.timestamp, reverse=True)
        
        return results
    
    def search_by_date_range(
        self,
        start_date: datetime,
        end_date: datetime,
        user_id: Optional[str] = None
    ) -> List[TranslationResult]:
        """
        Search by date range.
        
        Args:
            start_date: Start date
            end_date: End date
            user_id: Optional user ID to limit search scope
        
        Returns:
            List of matching TranslationResult objects
            
        Validates: Requirement 13.1
        """
        # Convert datetime to ISO format strings
        start_str = start_date.isoformat()
        end_str = end_date.isoformat()
        
        # Search using repository
        sessions = self.translation_repo.search_sessions(
            user_id=user_id,
            start_date=start_str,
            end_date=end_str
        )
        
        # Convert to TranslationResult objects
        results = [TranslationResult.from_dict(s) for s in sessions]
        
        # Sort by timestamp (newest first)
        results.sort(key=lambda x: x.timestamp, reverse=True)
        
        return results
    
    def search_by_session_token(
        self,
        token: str,
        user_id: Optional[str] = None
    ) -> Optional[TranslationResult]:
        """
        Search by session token.
        
        Args:
            token: Session token to search for
            user_id: Optional user ID to verify ownership
        
        Returns:
            TranslationResult if found, None otherwise
            
        Validates: Requirement 13.1
        """
        session_data = self.translation_repo.get_session_by_token(token)
        
        if not session_data:
            return None
        
        # Verify ownership if user_id is provided
        if user_id and session_data.get('user_id') != user_id:
            return None
        
        return TranslationResult.from_dict(session_data)
    
    def _filter_by_query(self, sessions: List[Dict], query: str) -> List[Dict]:
        """
        Filter sessions by query string.
        
        Searches in:
        - Session token
        - Filenames in metadata
        - User ID
        
        Args:
            sessions: List of session dictionaries
            query: Query string
        
        Returns:
            Filtered list of sessions
        """
        query_lower = query.lower()
        matching_sessions = []
        
        for session in sessions:
            # Check session token
            if query_lower in session.get('session_token', '').lower():
                matching_sessions.append(session)
                continue
            
            # Check user ID
            if query_lower in session.get('user_id', '').lower():
                matching_sessions.append(session)
                continue
            
            # Check filenames in metadata
            metadata = session.get('metadata', {})
            files = metadata.get('files', [])
            
            for filename in files:
                if query_lower in filename.lower():
                    matching_sessions.append(session)
                    break
        
        return matching_sessions
    
    def get_search_stats(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get search statistics without returning full results.
        
        Args:
            query: Search query string
            filters: Optional filters
            user_id: Optional user ID to limit search scope
        
        Returns:
            Dictionary with search statistics
            
        Validates: Requirement 13.5
        """
        results = self.search(query, filters, user_id)
        
        total_files = sum(r.file_count for r in results)
        total_size = sum(r.total_size for r in results)
        
        return {
            "total_sessions": len(results),
            "total_files": total_files,
            "total_size": total_size,
            "query": query,
            "filters": filters or {}
        }
    
    def highlight_matches(
        self,
        text: str,
        query: str,
        highlight_tag: str = "mark"
    ) -> str:
        """
        Highlight matching terms in text.
        
        Args:
            text: Text to highlight
            query: Query string
            highlight_tag: HTML tag to use for highlighting
        
        Returns:
            Text with highlighted matches
            
        Validates: Requirement 13.2
        """
        if not query:
            return text
        
        # Escape special regex characters
        escaped_query = re.escape(query)
        
        # Case-insensitive replacement
        pattern = re.compile(f'({escaped_query})', re.IGNORECASE)
        highlighted = pattern.sub(f'<{highlight_tag}>\\1</{highlight_tag}>', text)
        
        return highlighted
