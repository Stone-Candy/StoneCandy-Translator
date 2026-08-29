"""
会话管理服务（SessionService）

管理用户登录会话、令牌生成和验证。
"""

import logging
import secrets
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from uuid import uuid4

from manga_translator.server.core.models import Session
from manga_translator.server.core.persistence import atomic_write_json, load_json

logger = logging.getLogger(__name__)


class SessionService:
    """会话管理服务"""
    
    def __init__(
        self,
        sessions_file: Optional[str] = None,
        session_timeout_minutes: int = 60,
        enable_persistence: bool = False
    ):
        """
        初始化会话管理服务
        
        Args:
            sessions_file: 会话存储文件路径（可选，用于持久化）
            session_timeout_minutes: 会话超时时间（分钟）
            enable_persistence: 是否启用会话持久化
        """
        self.sessions_file = sessions_file
        self.session_timeout_minutes = session_timeout_minutes
        self.enable_persistence = enable_persistence
        
        # 内存中的会话存储: token -> Session
        self.sessions_by_token: Dict[str, Session] = {}
        # 按会话ID索引: session_id -> Session
        self.sessions_by_id: Dict[str, Session] = {}
        # 按用户名索引: username -> List[Session]
        self.sessions_by_username: Dict[str, List[Session]] = {}
        
        # 如果启用持久化，加载会话
        if self.enable_persistence and self.sessions_file:
            self._load_sessions()
    
    def create_session(
        self,
        username: str,
        role: str,
        ip_address: str,
        user_agent: str
    ) -> Session:
        """
        创建新会话
        
        Args:
            username: 用户名
            role: 用户角色
            ip_address: IP地址
            user_agent: 用户代理字符串
        
        Returns:
            Session: 创建的会话对象
        """
        # 生成唯一的会话ID和令牌
        session_id = str(uuid4())
        token = secrets.token_urlsafe(32)
        
        # 创建会话对象
        from datetime import timezone
        now = datetime.now(timezone.utc)
        session = Session(
            session_id=session_id,
            username=username,
            role=role,
            token=token,
            created_at=now,
            last_activity=now,
            ip_address=ip_address,
            user_agent=user_agent,
            is_active=True
        )
        
        # 保存到内存索引
        self.sessions_by_token[token] = session
        self.sessions_by_id[session_id] = session
        
        if username not in self.sessions_by_username:
            self.sessions_by_username[username] = []
        self.sessions_by_username[username].append(session)
        
        # 持久化（如果启用）
        if self.enable_persistence:
            self._save_sessions()
        
        logger.info(f"Created session for user: {username} (session_id: {session_id})")
        return session
    
    def get_session(self, token: str) -> Optional[Session]:
        """
        根据令牌获取会话
        
        Args:
            token: 会话令牌
        
        Returns:
            Optional[Session]: 会话对象，如果不存在或已过期返回 None
        """
        session = self.sessions_by_token.get(token)
        
        if not session:
            return None
        
        # 检查会话是否过期
        if self._is_session_expired(session):
            logger.debug(f"Session expired: {session.session_id}")
            self._deactivate_session(session)
            return None
        
        return session
    
    def get_session_by_id(self, session_id: str) -> Optional[Session]:
        """
        根据会话ID获取会话
        
        Args:
            session_id: 会话ID
        
        Returns:
            Optional[Session]: 会话对象，如果不存在返回 None
        """
        return self.sessions_by_id.get(session_id)
    
    def list_sessions(self, username: Optional[str] = None) -> List[Session]:
        """
        列出活动会话
        
        Args:
            username: 可选，只列出指定用户的会话
        
        Returns:
            List[Session]: 活动会话列表
        """
        if username:
            # 返回指定用户的活动会话
            user_sessions = self.sessions_by_username.get(username, [])
            return [s for s in user_sessions if s.is_active and not self._is_session_expired(s)]
        else:
            # 返回所有活动会话
            return [
                s for s in self.sessions_by_token.values()
                if s.is_active and not self._is_session_expired(s)
            ]
    
    def update_activity(self, token: str) -> bool:
        """
        更新会话活动时间
        
        Args:
            token: 会话令牌
        
        Returns:
            bool: 更新是否成功
        """
        session = self.sessions_by_token.get(token)
        
        if not session or not session.is_active:
            return False
        
        # 检查会话是否过期
        if self._is_session_expired(session):
            self._deactivate_session(session)
            return False
        
        # 更新最后活动时间
        from datetime import timezone
        session.last_activity = datetime.now(timezone.utc)
        
        # 持久化（如果启用）
        if self.enable_persistence:
            self._save_sessions()
        
        return True
    
    def terminate_session(self, session_id: str) -> bool:
        """
        终止指定会话
        
        Args:
            session_id: 会话ID
        
        Returns:
            bool: 终止是否成功
        """
        session = self.sessions_by_id.get(session_id)
        
        if not session:
            logger.warning(f"Session not found: {session_id}")
            return False
        
        # 标记为非活动
        self._deactivate_session(session)
        
        logger.info(f"Terminated session: {session_id} (user: {session.username})")
        return True
    
    def terminate_user_sessions(self, username: str) -> int:
        """
        终止用户的所有会话
        
        Args:
            username: 用户名
        
        Returns:
            int: 终止的会话数量
        """
        user_sessions = self.sessions_by_username.get(username, [])
        terminated_count = 0
        
        for session in user_sessions:
            if session.is_active:
                self._deactivate_session(session)
                terminated_count += 1
        
        logger.info(f"Terminated {terminated_count} session(s) for user: {username}")
        return terminated_count
    
    def cleanup_expired_sessions(self) -> int:
        """
        清理过期会话
        
        Returns:
            int: 清理的会话数量
        """
        expired_sessions = []
        
        for session in self.sessions_by_token.values():
            if session.is_active and self._is_session_expired(session):
                expired_sessions.append(session)
        
        for session in expired_sessions:
            self._deactivate_session(session)
        
        if expired_sessions:
            logger.info(f"Cleaned up {len(expired_sessions)} expired session(s)")
        
        return len(expired_sessions)
    
    def verify_token(self, token: str) -> Optional[Session]:
        """
        验证令牌并返回会话
        
        Args:
            token: 会话令牌
        
        Returns:
            Optional[Session]: 有效的会话对象，如果令牌无效返回 None
        """
        session = self.get_session(token)
        
        if session:
            # 更新活动时间
            self.update_activity(token)
        
        return session
    
    def clear_all_sessions(self) -> int:
        """
        清除所有会话（用于系统重启）
        
        Returns:
            int: 清除的会话数量
        """
        count = len([s for s in self.sessions_by_token.values() if s.is_active])
        
        self.sessions_by_token.clear()
        self.sessions_by_id.clear()
        self.sessions_by_username.clear()
        
        # 持久化（如果启用）
        if self.enable_persistence:
            self._save_sessions()
        
        logger.info(f"Cleared all sessions (count: {count})")
        return count
    
    def _is_session_expired(self, session: Session) -> bool:
        """
        检查会话是否过期
        
        Args:
            session: 会话对象
        
        Returns:
            bool: 会话是否过期
        """
        if not session.is_active:
            return True
        
        timeout = timedelta(minutes=self.session_timeout_minutes)
        from datetime import timezone
        return datetime.now(timezone.utc) - session.last_activity > timeout
    
    def _deactivate_session(self, session: Session) -> None:
        """
        停用会话
        
        Args:
            session: 会话对象
        """
        session.is_active = False
        
        # 从令牌索引中移除
        if session.token in self.sessions_by_token:
            del self.sessions_by_token[session.token]
        
        # 持久化（如果启用）
        if self.enable_persistence:
            self._save_sessions()
    
    def _load_sessions(self) -> None:
        """从持久化存储加载会话"""
        if not self.sessions_file:
            return
        
        try:
            data = load_json(self.sessions_file, default={'version': '1.0', 'sessions': []})
            
            sessions_data = data.get('sessions', [])
            
            for session_data in sessions_data:
                try:
                    session = Session.from_dict(session_data)
                    
                    # 只加载活动且未过期的会话
                    if session.is_active and not self._is_session_expired(session):
                        self.sessions_by_token[session.token] = session
                        self.sessions_by_id[session.session_id] = session
                        
                        if session.username not in self.sessions_by_username:
                            self.sessions_by_username[session.username] = []
                        self.sessions_by_username[session.username].append(session)
                except Exception as e:
                    logger.error(f"Failed to load session: {e}")
            
            active_count = len(self.sessions_by_token)
            logger.info(f"Loaded {active_count} active session(s)")
        except Exception as e:
            logger.error(f"Failed to load sessions: {e}")
    
    def _save_sessions(self) -> None:
        """保存会话到持久化存储"""
        if not self.sessions_file:
            return
        
        try:
            # 只保存活动会话
            active_sessions = [
                s for s in self.sessions_by_id.values()
                if s.is_active
            ]
            
            data = {
                'version': '1.0',
                'sessions': [session.to_dict() for session in active_sessions]
            }
            
            success = atomic_write_json(self.sessions_file, data, create_backup=False)
            if success:
                logger.debug(f"Saved {len(active_sessions)} session(s)")
            else:
                logger.error("Failed to save sessions")
        except Exception as e:
            logger.error(f"Failed to save sessions: {e}")
