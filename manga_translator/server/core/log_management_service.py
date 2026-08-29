"""
日志管理服务 (Log Management Service)

负责管理系统日志和对话框日志，包括：
- 记录翻译事件
- 查询和检索日志
- 导出日志
- 实时日志推送

需求: 31.1-31.6, 32.1-32.8, 33.1-33.8
"""

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from manga_translator.server.models import LogEntry
from manga_translator.server.repositories.log_repository import LogRepository


class LogManagementService:
    """日志管理服务类"""
    
    def __init__(self, log_repository: LogRepository):
        """
        初始化日志管理服务
        
        Args:
            log_repository: 日志数据仓库
        """
        self.log_repo = log_repository
    
    def log_translation_event(self, session_token: str, user_id: str,
                             event_type: str, message: str, level: str = 'info',
                             details: Optional[Dict[str, Any]] = None) -> LogEntry:
        """
        记录翻译事件
        
        Args:
            session_token: 会话令牌
            user_id: 用户ID
            event_type: 事件类型 (translation_start, translation_progress, 
                       translation_complete, translation_error, etc.)
            message: 日志消息
            level: 日志级别 (info, warning, error)
            details: 详细信息字典
        
        Returns:
            创建的日志条目
        
        需求: 31.2, 33.2
        """
        # 验证日志级别
        valid_levels = ['info', 'warning', 'error']
        if level not in valid_levels:
            raise ValueError(f"Invalid log level: {level}. Must be one of {valid_levels}")
        
        # 创建日志条目
        log_entry = LogEntry.create(
            session_token=session_token,
            user_id=user_id,
            level=level,
            event_type=event_type,
            message=message,
            details=details
        )
        
        # 保存到仓库
        self.log_repo.add_log(log_entry)
        
        return log_entry
    
    def get_session_logs(self, session_token: str, user_id: str,
                        is_admin: bool = False) -> List[Dict[str, Any]]:
        """
        获取对话框日志
        
        Args:
            session_token: 会话令牌
            user_id: 请求用户ID
            is_admin: 是否为管理员
        
        Returns:
            日志列表
        
        需求: 31.1, 32.4, 33.1, 35.3-35.8
        """
        # 获取会话日志
        logs = self.log_repo.get_session_logs(session_token)
        
        # 如果不是管理员，验证所有权
        if not is_admin and logs:
            # 检查第一条日志的用户ID（所有日志应该属于同一用户）
            if logs[0].get('user_id') != user_id:
                raise PermissionError(f"User {user_id} does not have permission to view logs for session {session_token}")
        
        # 按时间戳排序
        logs.sort(key=lambda x: x.get('timestamp', ''))
        
        return logs
    
    def get_user_logs(self, user_id: str, level: Optional[str] = None,
                     start_time: Optional[str] = None,
                     end_time: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取用户的所有日志
        
        Args:
            user_id: 用户ID
            level: 可选的日志级别过滤
            start_time: 可选的开始时间
            end_time: 可选的结束时间
        
        Returns:
            日志列表
        
        需求: 31.3, 34.1
        """
        logs = self.log_repo.search_logs(
            user_id=user_id,
            level=level,
            start_time=start_time,
            end_time=end_time
        )
        
        # 按时间戳排序
        logs.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        
        return logs
    
    def get_system_logs(self, level: Optional[str] = None,
                       start_time: Optional[str] = None,
                       end_time: Optional[str] = None,
                       limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        获取系统日志（管理员）
        
        Args:
            level: 可选的日志级别过滤
            start_time: 可选的开始时间
            end_time: 可选的结束时间
            limit: 可选的结果数量限制
        
        Returns:
            日志列表
        
        需求: 31.1-31.6, 32.1
        """
        logs = self.log_repo.search_logs(
            level=level,
            start_time=start_time,
            end_time=end_time
        )
        
        # 按时间戳排序（最新的在前）
        logs.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        
        # 应用限制
        if limit:
            logs = logs[:limit]
        
        return logs
    
    def get_all_sessions_logs(self, user_id: Optional[str] = None,
                             start_time: Optional[str] = None,
                             end_time: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
        """
        获取所有对话框日志（管理员）
        
        Args:
            user_id: 可选的用户ID过滤
            start_time: 可选的开始时间
            end_time: 可选的结束时间
        
        Returns:
            按会话令牌分组的日志字典
        
        需求: 32.1-32.8
        """
        logs = self.log_repo.search_logs(
            user_id=user_id,
            start_time=start_time,
            end_time=end_time
        )
        
        # 按会话令牌分组
        sessions_logs = {}
        for log in logs:
            session_token = log.get('session_token')
            if session_token not in sessions_logs:
                sessions_logs[session_token] = []
            sessions_logs[session_token].append(log)
        
        # 对每个会话的日志按时间排序
        for session_token in sessions_logs:
            sessions_logs[session_token].sort(key=lambda x: x.get('timestamp', ''))
        
        return sessions_logs
    
    def search_logs(self, user_id: Optional[str] = None,
                   session_token: Optional[str] = None,
                   level: Optional[str] = None,
                   event_type: Optional[str] = None,
                   start_time: Optional[str] = None,
                   end_time: Optional[str] = None,
                   keyword: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        搜索日志
        
        Args:
            user_id: 用户ID过滤
            session_token: 会话令牌过滤
            level: 日志级别过滤
            event_type: 事件类型过滤
            start_time: 开始时间
            end_time: 结束时间
            keyword: 关键词搜索（在消息中）
        
        Returns:
            匹配的日志列表
        
        需求: 31.3, 32.3
        """
        # 基础搜索
        logs = self.log_repo.search_logs(
            user_id=user_id,
            session_token=session_token,
            level=level,
            start_time=start_time,
            end_time=end_time
        )
        
        # 额外过滤
        if event_type:
            logs = [log for log in logs if log.get('event_type') == event_type]
        
        if keyword:
            keyword_lower = keyword.lower()
            logs = [log for log in logs 
                   if keyword_lower in log.get('message', '').lower()]
        
        # 按时间戳排序
        logs.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        
        return logs
    
    def export_session_logs(self, session_token: str, user_id: str,
                           is_admin: bool = False, format: str = 'json') -> bytes:
        """
        导出单个对话框日志
        
        Args:
            session_token: 会话令牌
            user_id: 请求用户ID
            is_admin: 是否为管理员
            format: 导出格式 (json 或 txt)
        
        Returns:
            日志文件内容（字节）
        
        需求: 31.5, 33.8
        """
        # 获取日志（包含权限检查）
        logs = self.get_session_logs(session_token, user_id, is_admin)
        
        if format == 'json':
            # JSON格式
            content = json.dumps(logs, indent=2, ensure_ascii=False)
            return content.encode('utf-8')
        elif format == 'txt':
            # 文本格式
            lines = []
            lines.append(f"Session Logs: {session_token}")
            lines.append(f"Exported at: {datetime.now(timezone.utc).isoformat()}")
            lines.append("=" * 80)
            lines.append("")
            
            for log in logs:
                lines.append(f"[{log.get('timestamp')}] [{log.get('level').upper()}] {log.get('event_type')}")
                lines.append(f"  {log.get('message')}")
                if log.get('details'):
                    lines.append(f"  Details: {json.dumps(log.get('details'), ensure_ascii=False)}")
                lines.append("")
            
            content = '\n'.join(lines)
            return content.encode('utf-8')
        else:
            raise ValueError(f"Unsupported export format: {format}")
    
    def export_multiple_sessions_logs(self, session_tokens: List[str],
                                     user_id: str, is_admin: bool = False,
                                     format: str = 'json') -> bytes:
        """
        批量导出多个对话框日志
        
        Args:
            session_tokens: 会话令牌列表
            user_id: 请求用户ID
            is_admin: 是否为管理员
            format: 导出格式 (json 或 txt)
        
        Returns:
            日志文件内容（字节）
        
        需求: 32.8
        """
        all_logs = {}
        
        for session_token in session_tokens:
            try:
                logs = self.get_session_logs(session_token, user_id, is_admin)
                all_logs[session_token] = logs
            except PermissionError:
                # 跳过无权限的会话
                continue
        
        if format == 'json':
            content = json.dumps(all_logs, indent=2, ensure_ascii=False)
            return content.encode('utf-8')
        elif format == 'txt':
            lines = []
            lines.append("Multiple Session Logs Export")
            lines.append(f"Exported at: {datetime.now(timezone.utc).isoformat()}")
            lines.append(f"Total sessions: {len(all_logs)}")
            lines.append("=" * 80)
            lines.append("")
            
            for session_token, logs in all_logs.items():
                lines.append(f"\n{'=' * 80}")
                lines.append(f"Session: {session_token}")
                lines.append(f"{'=' * 80}\n")
                
                for log in logs:
                    lines.append(f"[{log.get('timestamp')}] [{log.get('level').upper()}] {log.get('event_type')}")
                    lines.append(f"  {log.get('message')}")
                    if log.get('details'):
                        lines.append(f"  Details: {json.dumps(log.get('details'), ensure_ascii=False)}")
                    lines.append("")
            
            content = '\n'.join(lines)
            return content.encode('utf-8')
        else:
            raise ValueError(f"Unsupported export format: {format}")
    
    def get_log_statistics(self, user_id: Optional[str] = None,
                          start_time: Optional[str] = None,
                          end_time: Optional[str] = None) -> Dict[str, Any]:
        """
        获取日志统计信息
        
        Args:
            user_id: 可选的用户ID过滤
            start_time: 可选的开始时间
            end_time: 可选的结束时间
        
        Returns:
            统计信息字典
        
        需求: 31.6, 32.2
        """
        logs = self.log_repo.search_logs(
            user_id=user_id,
            start_time=start_time,
            end_time=end_time
        )
        
        # 统计各级别日志数量
        level_counts = {'info': 0, 'warning': 0, 'error': 0}
        event_type_counts = {}
        session_count = set()
        user_count = set()
        
        for log in logs:
            level = log.get('level', 'info')
            level_counts[level] = level_counts.get(level, 0) + 1
            
            event_type = log.get('event_type', 'unknown')
            event_type_counts[event_type] = event_type_counts.get(event_type, 0) + 1
            
            session_count.add(log.get('session_token'))
            user_count.add(log.get('user_id'))
        
        return {
            'total_logs': len(logs),
            'level_counts': level_counts,
            'event_type_counts': event_type_counts,
            'unique_sessions': len(session_count),
            'unique_users': len(user_count),
            'time_range': {
                'start': start_time,
                'end': end_time
            }
        }
    
    def clear_session_logs(self, session_token: str, user_id: str,
                          is_admin: bool = False) -> int:
        """
        清空对话框日志
        
        Args:
            session_token: 会话令牌
            user_id: 请求用户ID
            is_admin: 是否为管理员
        
        Returns:
            删除的日志数量
        
        需求: 33.6
        """
        # 先验证权限
        self.get_session_logs(session_token, user_id, is_admin)
        
        # 删除日志
        deleted_count = self.log_repo.delete_session_logs(session_token)
        
        return deleted_count
    
    def cleanup_old_logs(self, days: int = 30) -> int:
        """
        清理旧日志
        
        Args:
            days: 保留天数
        
        Returns:
            删除的日志数量
        """
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=days)
        cutoff_timestamp = cutoff_time.isoformat()
        
        deleted_count = self.log_repo.delete_old_logs(cutoff_timestamp)
        
        return deleted_count
