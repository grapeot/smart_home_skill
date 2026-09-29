"""Wemo scheduled task manager using APScheduler and YAML config."""

import yaml
import logging
import pytz
import os
from typing import Dict, List, Optional
from pathlib import Path
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from services.wemo_service import wemo_service

logger = logging.getLogger(__name__)

# Pacific timezone
PACIFIC_TZ = pytz.timezone('America/Los_Angeles')

class WemoScheduleManager:
    """Manage Wemo scheduled tasks with APScheduler."""
    
    def __init__(self, config_file: str = "config/wemo_config.yaml"):
        """
        Initialize the scheduled task manager.
        
        Args:
            config_file: YAML config path relative to the project root.
        """
        self.config_file = config_file
        self.devices: Dict[str, any] = {}
        self.scheduler: Optional[BackgroundScheduler] = None
        self.config: Optional[Dict] = None
        
    def register_device(self, name: str, device):
        """
        Register one Wemo device.
        
        Args:
            name: Device name used in config references.
            device: pywemo device object.
        """
        self.devices[name.lower()] = device
        logger.info(f"Registered device: {name}")
    
    def load_config(self) -> Optional[Dict]:
        """
        Load the YAML config file.
        
        Returns:
            Config dict, or None if loading fails.
        """
        config_path = Path(self.config_file)
        
        if not config_path.exists():
            logger.warning(f"Config file does not exist: {self.config_file}")
            return None
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            logger.info(f"Loaded config file: {self.config_file}")
            return config
        except Exception as e:
            logger.error(f"Error reading config file: {str(e)}")
            import traceback
            traceback.print_exc()
            return None
    
    def execute_task(self, device_name: str, action: str):
        """
        Execute one scheduled task.

        Args:
            device_name: Device name.
            action: Action, either on or off.
        """
        if action == 'on':
            result = wemo_service.turn_on(device_name)
        elif action == 'off':
            result = wemo_service.turn_off(device_name)
        else:
            logger.error(f"Unknown scheduled action: {action} for {device_name}")
            return

        if result.get("status") == "success":
            logger.info(f"Scheduled task executed: {device_name} {action}")
        else:
            logger.error(f"Scheduled task failed: {device_name} {action}: {result.get('message')}")
    
    def start(self):
        """Start the scheduled task manager."""
        if self.scheduler and self.scheduler.running:
            logger.warning("Scheduled task manager is already running")
            return
        
        # Load config file.
        self.config = self.load_config()
        
        if not self.config:
            logger.info("No config file, skipping scheduled task initialization")
            return
        
        schedule_config = self.config.get('schedule', {})
        tasks = schedule_config.get('tasks', [])
        
        if not tasks:
            logger.info("No scheduled tasks to run")
            return
        
        # Resolve timezone.
        timezone_str = schedule_config.get('timezone', 'Pacific')
        if timezone_str.lower() == 'pacific':
            timezone = PACIFIC_TZ
        elif timezone_str.lower() == 'utc':
            timezone = pytz.UTC
        else:
            timezone = pytz.timezone('America/Los_Angeles')
        
        # Create scheduler.
        self.scheduler = BackgroundScheduler(timezone=timezone)
        
        # Add tasks.
        for task in tasks:
            try:
                time_str = task.get('time', '')
                device_name = task.get('device', '')
                action = task.get('action', '')
                
                if not all([time_str, device_name, action]):
                    logger.warning(f"Incomplete task config, skipping: {task}")
                    continue
                
                # Parse time.
                time_parts = time_str.split(':')
                hour = int(time_parts[0])
                minute = int(time_parts[1]) if len(time_parts) > 1 else 0
                second = int(time_parts[2]) if len(time_parts) > 2 else 0
                
                # Create task ID.
                task_id = f"{device_name}_{action}_{time_str.replace(':', '')}"
                
                # Create CronTrigger.
                trigger = CronTrigger(
                    hour=hour,
                    minute=minute,
                    second=second,
                    timezone=timezone
                )
                
                # Add task.
                self.scheduler.add_job(
                    func=lambda d=device_name, a=action: self.execute_task(d, a),
                    trigger=trigger,
                    id=task_id,
                    name=f"{device_name} {action} at {time_str}"
                )
                
                logger.info(f"Scheduled task: {time_str} {device_name} {action}")
                
            except Exception as e:
                logger.error(f"Error adding task: {str(e)}")
                import traceback
                traceback.print_exc()
        
        # Start scheduler.
        self.scheduler.start()
        logger.info("Scheduled task manager started")
    
    def stop(self):
        """Stop the scheduled task manager."""
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Scheduled task manager stopped")
    
    def get_scheduled_tasks(self) -> List[Dict]:
        """Return all scheduled task records."""
        if not self.scheduler or not self.scheduler.running:
            return []
        
        tasks = []
        for job in self.scheduler.get_jobs():
            # Extract task info from the job name.
            name_parts = job.name.split()
            if len(name_parts) >= 3:
                device = name_parts[0]
                action = name_parts[1]
                time_str = ' '.join(name_parts[3:]) if len(name_parts) > 3 else ''
                
                tasks.append({
                    'time': time_str,
                    'device': device,
                    'action': action,
                    'timezone': str(self.scheduler.timezone) if self.scheduler.timezone else 'Pacific',
                    'next_run': str(job.next_run_time) if job.next_run_time else 'N/A'
                })
            else:
                tasks.append({
                    'job_id': job.id,
                    'name': job.name,
                    'next_run': str(job.next_run_time) if job.next_run_time else 'N/A'
                })
        
        return tasks
