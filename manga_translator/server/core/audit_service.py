"""
审计日志服务（AuditService）

记录和查询审计日志，支持日志筛选、导出和轮转功能。
"""

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from manga_translator.server.core.models import AuditEvent

logger = logging.getLogger(__name__)


class AuditService:
    """审计日志服务"""
    
    def __init__(
        self,
        audit_log_file: str = "manga_translator/server/data/audit.log",
        max_log_size_mb: int = 10,
        max_backup_files: int = 5
    ):
        """
        初始化审计日志服务
        
        Args:
            audit_log_file: 审计日志文件路径
            max_log_size_mb: 日志文件最大大小（MB），超过后自动轮转
            max_backup_files: 保留的备份文件数量
        """
        self.audit_log_file = audit_log_file
        self.max_log_size_bytes = max_log_size_mb * 1024 * 1024
        self.max_backup_files = max_backup_files
        
        # 确保日志文件目录存在
        log_dir = Path(audit_log_file).parent
        if log_dir and not log_dir.exists():
            log_dir.mkdir(parents=True, exist_ok=True)
        
        # 确保日志文件存在
        if not Path(audit_log_file).exists():
            Path(audit_log_file).touch()
    
    def log_event(
        self,
        event_type: str,
        username: str,
        ip_address: str,
        details: Dict[str, Any],
        result: str
    ) -> AuditEvent:
        """
        记录审计事件
        
        Args:
            event_type: 事件类型（如 'login', 'logout', 'create_task', 'permission_change'）
            username: 用户名
            ip_address: IP地址
            details: 事件详细信息
            result: 结果（'success' 或 'failure'）
        
        Returns:
            AuditEvent: 创建的审计事件对象
        """
        # 创建审计事件
        event = AuditEvent(
            event_id=str(uuid4()),
            timestamp=datetime.now(timezone.utc),
            event_type=event_type,
            username=username,
            ip_address=ip_address,
            details=details,
            result=result
        )
        
        # 写入日志文件
        try:
            with open(self.audit_log_file, 'a', encoding='utf-8') as f:
                f.write(event.to_json_line() + '\n')
            
            # 检查是否需要轮转
            self._check_and_rotate()
            
            logger.debug(
                f"Logged audit event: {event_type} by {username} - {result}"
            )
        except Exception as e:
            logger.error(f"Failed to log audit event: {e}")
        
        return event
    
    def query_events(
        self,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[AuditEvent]:
        """
        查询审计事件
        
        Args:
            filters: 筛选条件字典，支持的键:
                - username: 用户名
                - event_type: 事件类型
                - result: 结果（'success' 或 'failure'）
                - start_time: 开始时间（datetime）
                - end_time: 结束时间（datetime）
            limit: 返回的最大事件数
            offset: 跳过的事件数（用于分页）
        
        Returns:
            List[AuditEvent]: 符合条件的审计事件列表
        """
        if filters is None:
            filters = {}
        
        events = []
        
        try:
            with open(self.audit_log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # 解析每一行
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                try:
                    event_data = json.loads(line)
                    event = AuditEvent.from_dict(event_data)
                    
                    # 应用筛选条件
                    if self._matches_filters(event, filters):
                        events.append(event)
                except Exception as e:
                    logger.warning(f"Failed to parse audit log line: {e}")
                    continue
            
            # 按时间倒序排序（最新的在前）
            events.sort(key=lambda e: e.timestamp, reverse=True)
            
            # 应用分页
            return events[offset:offset + limit]
        
        except FileNotFoundError:
            logger.warning(f"Audit log file not found: {self.audit_log_file}")
            return []
        except Exception as e:
            logger.error(f"Failed to query audit events: {e}")
            return []
    
    def export_events(
        self,
        filters: Optional[Dict[str, Any]] = None,
        format: str = 'json'
    ) -> str:
        """
        导出审计事件
        
        Args:
            filters: 筛选条件（同 query_events）
            format: 导出格式（'json' 或 'csv'）
        
        Returns:
            str: 导出的数据字符串
        """
        events = self.query_events(filters=filters, limit=10000)
        
        if format == 'json':
            return self._export_json(events)
        elif format == 'csv':
            return self._export_csv(events)
        else:
            raise ValueError(f"Unsupported export format: {format}")
    
    def rotate_log_file(self) -> bool:
        """
        手动轮转日志文件
        
        Returns:
            bool: 轮转是否成功
        """
        try:
            if not Path(self.audit_log_file).exists():
                logger.warning("Audit log file does not exist, nothing to rotate")
                return False
            
            # 生成备份文件名（带时间戳）
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_file = f"{self.audit_log_file}.{timestamp}"
            
            # 移动当前日志文件到备份
            shutil.move(self.audit_log_file, backup_file)
            
            # 创建新的日志文件
            Path(self.audit_log_file).touch()
            
            logger.info(f"Rotated audit log: {backup_file}")
            
            # 清理旧的备份文件
            self._cleanup_old_backups()
            
            return True
        except Exception as e:
            logger.error(f"Failed to rotate audit log: {e}")
            return False
    
    def _matches_filters(
        self,
        event: AuditEvent,
        filters: Dict[str, Any]
    ) -> bool:
        """
        检查事件是否匹配筛选条件
        
        Args:
            event: 审计事件
            filters: 筛选条件
        
        Returns:
            bool: 是否匹配
        """
        # 用户名筛选
        if 'username' in filters:
            if event.username != filters['username']:
                return False
        
        # 事件类型筛选
        if 'event_type' in filters:
            if event.event_type != filters['event_type']:
                return False
        
        # 结果筛选
        if 'result' in filters:
            if event.result != filters['result']:
                return False
        
        # 时间范围筛选
        if 'start_time' in filters:
            if event.timestamp < filters['start_time']:
                return False
        
        if 'end_time' in filters:
            if event.timestamp > filters['end_time']:
                return False
        
        return True
    
    def _check_and_rotate(self) -> None:
        """检查日志文件大小，如果超过限制则轮转"""
        try:
            file_size = Path(self.audit_log_file).stat().st_size
            
            if file_size > self.max_log_size_bytes:
                logger.info(
                    f"Audit log size ({file_size} bytes) exceeds limit "
                    f"({self.max_log_size_bytes} bytes), rotating..."
                )
                self.rotate_log_file()
        except Exception as e:
            logger.error(f"Failed to check log file size: {e}")
    
    def _cleanup_old_backups(self) -> None:
        """清理旧的备份文件，只保留最新的 N 个"""
        try:
            log_dir = Path(self.audit_log_file).parent
            log_name = Path(self.audit_log_file).name
            
            # 查找所有备份文件
            backup_files = sorted(
                log_dir.glob(f"{log_name}.*"),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )
            
            # 删除超过限制的备份文件
            for backup_file in backup_files[self.max_backup_files:]:
                try:
                    backup_file.unlink()
                    logger.info(f"Deleted old backup: {backup_file}")
                except Exception as e:
                    logger.error(f"Failed to delete backup {backup_file}: {e}")
        except Exception as e:
            logger.error(f"Failed to cleanup old backups: {e}")
    
    def _export_json(self, events: List[AuditEvent]) -> str:
        """导出为 JSON 格式"""
        data = [event.to_dict() for event in events]
        return json.dumps(data, ensure_ascii=False, indent=2)
    
    def _export_csv(self, events: List[AuditEvent]) -> str:
        """导出为 CSV 格式"""
        if not events:
            return ""
        
        # CSV 头部
        lines = [
            "event_id,timestamp,event_type,username,ip_address,result,details"
        ]
        
        # CSV 数据行
        for event in events:
            details_str = json.dumps(event.details, ensure_ascii=False).replace('"', '""')
            line = (
                f'"{event.event_id}",'
                f'"{event.timestamp.isoformat()}",'
                f'"{event.event_type}",'
                f'"{event.username}",'
                f'"{event.ip_address}",'
                f'"{event.result}",'
                f'"{details_str}"'
            )
            lines.append(line)
        
        return '\n'.join(lines)
