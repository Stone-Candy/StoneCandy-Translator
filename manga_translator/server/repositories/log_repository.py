"""
Repository for log management.
"""

from typing import List, Optional

from manga_translator.server.models import LogEntry
from manga_translator.server.repositories.base_repository import BaseJSONRepository


class LogRepository(BaseJSONRepository):
    """Repository for managing logs."""
    
    def _get_default_structure(self):
        """Get default structure for log file."""
        return {
            "logs": [],
            "last_updated": None
        }
    
    def add_log(self, log_entry: LogEntry) -> None:
        """Add a log entry."""
        self.add("logs", log_entry.to_dict())
    
    def get_session_logs(self, session_token: str) -> List[dict]:
        """Get all logs for a specific session."""
        return self.find_by_field("logs", "session_token", session_token)
    
    def get_user_logs(self, user_id: str) -> List[dict]:
        """Get all logs for a specific user."""
        return self.find_by_field("logs", "user_id", user_id)
    
    def get_logs_by_level(self, level: str) -> List[dict]:
        """Get logs by level (info, warning, error)."""
        return self.find_by_field("logs", "level", level)
    
    def get_all_logs(self) -> List[dict]:
        """Get all logs."""
        return self.query("logs")
    
    def search_logs(self, user_id: Optional[str] = None,
                   session_token: Optional[str] = None,
                   level: Optional[str] = None,
                   start_time: Optional[str] = None,
                   end_time: Optional[str] = None) -> List[dict]:
        """Search logs with filters."""
        def filter_func(log):
            if user_id and log.get('user_id') != user_id:
                return False
            if session_token and log.get('session_token') != session_token:
                return False
            if level and log.get('level') != level:
                return False
            if start_time and log.get('timestamp', '') < start_time:
                return False
            if end_time and log.get('timestamp', '') > end_time:
                return False
            return True
        
        return self.query("logs", filter_func)
    
    def delete_session_logs(self, session_token: str) -> int:
        """Delete all logs for a specific session. Returns count of deleted logs."""
        data = self._read_data()
        logs = data.get("logs", [])
        original_count = len(logs)
        
        data["logs"] = [log for log in logs 
                       if log.get('session_token') != session_token]
        
        deleted_count = original_count - len(data["logs"])
        if deleted_count > 0:
            self._write_data(data)
        
        return deleted_count
    
    def delete_old_logs(self, before_timestamp: str) -> int:
        """Delete logs older than specified timestamp. Returns count of deleted logs."""
        data = self._read_data()
        logs = data.get("logs", [])
        original_count = len(logs)
        
        data["logs"] = [log for log in logs 
                       if log.get('timestamp', '') >= before_timestamp]
        
        deleted_count = original_count - len(data["logs"])
        if deleted_count > 0:
            self._write_data(data)
        
        return deleted_count
