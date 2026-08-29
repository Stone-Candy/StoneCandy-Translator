"""
配额调度器 (QuotaScheduler)

管理配额相关的定时任务，包括每日配额重置。
"""

import logging
import threading
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


class QuotaScheduler:
    """配额调度器 - 管理配额相关的定时任务"""
    
    def __init__(self, quota_service):
        """
        初始化配额调度器
        
        Args:
            quota_service: QuotaManagementService实例
        """
        self.quota_service = quota_service
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        logger.info("QuotaScheduler initialized")
    
    def start(self):
        """启动调度器"""
        if self._running:
            logger.warning("QuotaScheduler is already running")
            return
        
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self._thread.start()
        logger.info("QuotaScheduler started")
    
    def stop(self):
        """停止调度器"""
        if not self._running:
            return
        
        self._running = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("QuotaScheduler stopped")
    
    def _run_scheduler(self):
        """运行调度器主循环"""
        logger.info("QuotaScheduler main loop started")
        
        # 记录上次重置的日期
        last_reset_date = datetime.now(timezone.utc).date()
        
        while self._running:
            try:
                current_date = datetime.now(timezone.utc).date()
                
                # 检查是否需要重置配额（新的一天）
                if current_date > last_reset_date:
                    logger.info(f"New day detected, resetting daily quotas (last reset: {last_reset_date})")
                    self._reset_all_daily_quotas()
                    last_reset_date = current_date
                
                # 每小时检查一次
                if self._stop_event.wait(timeout=3600):  # 1 hour
                    break
                    
            except Exception as e:
                logger.error(f"Error in quota scheduler loop: {e}", exc_info=True)
                # 发生错误时等待一段时间再继续
                if self._stop_event.wait(timeout=60):  # 1 minute
                    break
        
        logger.info("QuotaScheduler main loop ended")
    
    def _reset_all_daily_quotas(self):
        """重置所有用户的每日配额"""
        try:
            success = self.quota_service.reset_daily_quota(user_id=None)
            if success:
                logger.info("Successfully reset all daily quotas")
            else:
                logger.error("Failed to reset daily quotas")
        except Exception as e:
            logger.error(f"Error resetting daily quotas: {e}", exc_info=True)
    
    def force_reset_now(self):
        """立即强制重置所有配额（手动触发）"""
        logger.info("Forcing immediate quota reset")
        self._reset_all_daily_quotas()
