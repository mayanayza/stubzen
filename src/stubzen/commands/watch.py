"""
Watch command for monitoring file changes and auto-regenerating stubs
"""

import logging
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from .. import config
from .generate import StubGenerateCommand
from ..config import StubzenConfig

logger = logging.getLogger(__name__)

class StubChangeHandler(FileSystemEventHandler):
    """Handler for file changes that trigger stub regeneration"""

    def __init__(self, project_root: str):
        self.project_root = project_root
        self.last_regeneration = 0
        self.debounce_time = 2  # seconds
        self.generate_command = StubGenerateCommand(project_root)

    def on_modified(self, event):
        if event.is_directory:
            return

        # Check if it's a Python file that might need stub regeneration
        if event.src_path.endswith('.py'):
            # Check for patterns that should trigger regeneration
            should_regenerate = (
                    'mixin' in event.src_path.lower() or
                    'layer.py' in event.src_path or
                    any(pattern in event.src_path for pattern in StubzenConfig().watch_patterns)
            )

            if should_regenerate:
                current_time = time.time()

                # Debounce rapid file changes
                if current_time - self.last_regeneration > self.debounce_time:
                    logger.info(f"\n🔄 Detected change in {event.src_path}")
                    self.regenerate_stubs()
                    self.last_regeneration = current_time

    def regenerate_stubs(self):
        """Regenerate type stubs"""
        try:
            logger.info("🔧 Regenerating type stubs...")

            success = self.generate_command.execute()

            if success:
                logger.info("✅ Type stubs regenerated successfully")
            else:
                logger.error("❌ Type stub regeneration failed")

        except Exception as e:
            logger.error(f"❌ Error regenerating stubs: {e}")

class StubWatchCommand:
    """Command to watch files and auto-regenerate stubs"""

    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root).resolve()

    def execute(self) -> bool:
        """Execute the watch command"""
        try:
            event_handler = StubChangeHandler(str(self.project_root))
            observer = Observer()

            # Use watch paths from config
            watch_paths = StubzenConfig().watch_paths

            watching_count = 0
            for path in watch_paths:
                full_path = self.project_root / path
                if full_path.exists():
                    observer.schedule(event_handler, str(full_path), recursive=True)
                    logger.info(f"👀 Watching {path} for changes...")
                    watching_count += 1
                else:
                    logger.warning(f"⚠️  Path {path} doesn't exist, skipping...")

            if watching_count == 0:
                logger.error("❌ No valid paths to watch found")
                return False

            observer.start()

            try:
                logger.info(f"\n🚀 File watcher started for {watching_count} paths")
                logger.info("Press Ctrl+C to stop watching...")

                # Generate initial stubs
                logger.info("\n🔧 Generating initial stubs...")
                event_handler.regenerate_stubs()

                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                observer.stop()
                logger.info("\n🛑 File watcher stopped.")

            observer.join()
            return True

        except Exception as e:
            logger.error(f"❌ File watcher failed to start: {e}")
            return False