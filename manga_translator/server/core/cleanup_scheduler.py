"""
Automatic Cleanup Scheduler

This module provides a scheduler for running automatic cleanup tasks.
It uses APScheduler to run cleanup operations on a daily schedule.
"""

import logging
from typing import Dict, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from manga_translator.server.core.cleanup_service import CleanupSchedulerService

logger = logging.getLogger(__name__)


class AutoCleanupScheduler:
    """
    Scheduler for automatic cleanup tasks.
    
    Validates: Requirements 6.2, 6.3, 6.5
    """
    
    def __init__(
        self,
        cleanup_service: Optional[CleanupSchedulerService] = None,
        user_group_mapping_provider: Optional[callable] = None
    ):
        """
        Initialize the automatic cleanup scheduler.
        
        Args:
            cleanup_service: Optional cleanup service instance
            user_group_mapping_provider: Optional function to get user group mapping
        """
        self.cleanup_service = cleanup_service or CleanupSchedulerService()
        self.user_group_mapping_provider = user_group_mapping_provider
        self.scheduler = BackgroundScheduler()
        self.is_running = False
        
        # Store cleanup reports
        self.last_cleanup_report = None
        self.cleanup_history = []
    
    def start(self, hour: int = 2, minute: int = 0):
        """
        Start the automatic cleanup scheduler.
        
        Args:
            hour: Hour of day to run cleanup (0-23), default 2 AM
            minute: Minute of hour to run cleanup (0-59), default 0
            
        Validates: Requirement 6.2 - Daily automatic cleanup
        """
        if self.is_running:
            logger.warning("Cleanup scheduler is already running")
            return
        
        # Add daily cleanup job
        trigger = CronTrigger(hour=hour, minute=minute)
        self.scheduler.add_job(
            self._run_cleanup,
            trigger=trigger,
            id='daily_cleanup',
            name='Daily Automatic Cleanup',
            replace_existing=True
        )
        
        # Start the scheduler
        self.scheduler.start()
        self.is_running = True
        
        logger.info(f"Automatic cleanup scheduler started (runs daily at {hour:02d}:{minute:02d})")
    
    def stop(self):
        """Stop the automatic cleanup scheduler."""
        if not self.is_running:
            logger.warning("Cleanup scheduler is not running")
            return
        
        self.scheduler.shutdown(wait=True)
        self.is_running = False
        
        logger.info("Automatic cleanup scheduler stopped")
    
    def _get_user_group_mapping(self) -> Dict[str, str]:
        """
        Get user to group mapping.
        
        Returns:
            Dictionary mapping user_id to user_group_id
        """
        if self.user_group_mapping_provider:
            try:
                return self.user_group_mapping_provider()
            except Exception as e:
                logger.error(f"Error getting user group mapping: {e}")
        
        return {}
    
    def _run_cleanup(self):
        """
        Execute the automatic cleanup task.
        
        This method is called by the scheduler.
        
        Validates: Requirements 6.2, 6.3, 6.5
        """
        logger.info("Starting scheduled automatic cleanup")
        
        try:
            # Get user group mapping
            user_group_mapping = self._get_user_group_mapping()
            
            # Run automatic cleanup
            report = self.cleanup_service.run_auto_cleanup(user_group_mapping)
            
            # Store report
            self.last_cleanup_report = report
            self.cleanup_history.append(report)
            
            # Keep only last 30 reports
            if len(self.cleanup_history) > 30:
                self.cleanup_history = self.cleanup_history[-30:]
            
            # Log summary
            logger.info(
                f"Automatic cleanup completed: "
                f"deleted {len(report.deleted_sessions)} sessions, "
                f"freed {report.freed_space_mb} MB"
            )
            
            if report.errors:
                logger.warning(f"Cleanup completed with {len(report.errors)} errors")
                for error in report.errors:
                    logger.error(f"Cleanup error: {error}")
        
        except Exception as e:
            logger.error(f"Error during automatic cleanup: {e}", exc_info=True)
    
    def run_now(self) -> Optional[dict]:
        """
        Run cleanup immediately (for testing or manual trigger).
        
        Returns:
            Cleanup report dictionary, or None if failed
        """
        logger.info("Running cleanup immediately")
        
        try:
            # Get user group mapping
            user_group_mapping = self._get_user_group_mapping()
            
            # Run automatic cleanup
            report = self.cleanup_service.run_auto_cleanup(user_group_mapping)
            
            # Store report
            self.last_cleanup_report = report
            self.cleanup_history.append(report)
            
            # Keep only last 30 reports
            if len(self.cleanup_history) > 30:
                self.cleanup_history = self.cleanup_history[-30:]
            
            logger.info(
                f"Manual cleanup trigger completed: "
                f"deleted {len(report.deleted_sessions)} sessions, "
                f"freed {report.freed_space_mb} MB"
            )
            
            return report.to_dict()
        
        except Exception as e:
            logger.error(f"Error during manual cleanup trigger: {e}", exc_info=True)
            return None
    
    def get_last_report(self) -> Optional[dict]:
        """
        Get the last cleanup report.
        
        Returns:
            Last cleanup report dictionary, or None if no cleanup has run
        """
        if self.last_cleanup_report:
            return self.last_cleanup_report.to_dict()
        return None
    
    def get_cleanup_history(self, limit: int = 10) -> list:
        """
        Get cleanup history.
        
        Args:
            limit: Maximum number of reports to return
        
        Returns:
            List of cleanup report dictionaries
        """
        reports = self.cleanup_history[-limit:]
        return [report.to_dict() for report in reports]
    
    def get_next_run_time(self) -> Optional[str]:
        """
        Get the next scheduled run time.
        
        Returns:
            ISO format timestamp of next run, or None if not scheduled
        """
        if not self.is_running:
            return None
        
        job = self.scheduler.get_job('daily_cleanup')
        if job and job.next_run_time:
            return job.next_run_time.isoformat()
        
        return None
    
    def get_status(self) -> dict:
        """
        Get scheduler status.
        
        Returns:
            Dictionary with scheduler status information
        """
        return {
            'is_running': self.is_running,
            'next_run_time': self.get_next_run_time(),
            'last_cleanup': self.get_last_report(),
            'total_cleanups': len(self.cleanup_history)
        }
