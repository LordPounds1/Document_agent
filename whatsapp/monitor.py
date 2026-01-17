"""
WhatsApp Monitor - background monitoring for new documents.

Uses subprocess to avoid asyncio issues on Windows.
The actual monitoring runs in monitor_worker.py.
"""

import contextlib
import json
import logging
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
logger = logging.getLogger(__name__)

RESULTS_FILE = Path("whatsapp_monitor_results.json")


@dataclass
class MonitorEvent:
    """Event from WhatsApp monitor."""
    event_type: str  # 'document_found', 'document_processed', 'error', 'status'
    timestamp: datetime = field(default_factory=datetime.now)
    data: dict = field(default_factory=dict)
    message: str = ""


class WhatsAppMonitor:
    """
    Background monitor for WhatsApp documents using subprocess.

    Starts a separate Python process that runs the monitoring loop.
    Results are saved to a JSON file which can be polled for updates.
    """

    def __init__(
        self,
        session_dir: str = '.whatsapp_session_playwright',
        downloads_dir: str = 'whatsapp_downloads',
        check_interval: int = 60,
        chat_limit: int = 10,
        on_document: Callable | None = None,
        on_event: Callable | None = None
    ):
        self.session_dir = session_dir
        self.downloads_dir = downloads_dir
        self.check_interval = check_interval
        self.chat_limit = chat_limit

        self.on_document = on_document
        self.on_event = on_event

        self._process: subprocess.Popen | None = None
        self._processed_files: set[str] = set()
        self._last_doc_count = 0

        self.stats: dict[str, int | datetime | None] = {
            'documents_found': 0,
            'documents_processed': 0,
            'errors': 0,
            'last_check': None,
            'checks_count': 0
        }

    @property
    def is_running(self) -> bool:
        """Check if monitor subprocess is running."""
        return self._process is not None and self._process.poll() is None

    @property
    def is_connected(self) -> bool:
        """Check if connected to WhatsApp (by reading results file)."""
        if not RESULTS_FILE.exists():
            return False
        try:
            data = json.loads(RESULTS_FILE.read_text(encoding='utf-8'))
            status = data.get('status')
            return isinstance(status, str) and status == 'monitoring'
        except Exception:
            return False

    def start(self) -> bool:
        """Start the monitoring subprocess."""
        if self.is_running:
            logger.warning("Monitor already running")
            return True

        # Clear old results
        if RESULTS_FILE.exists():
            # Keep processed files from previous session
            try:
                data = json.loads(RESULTS_FILE.read_text(encoding='utf-8'))
                for doc in data.get('documents', []):
                    if doc.get('file_path'):
                        self._processed_files.add(doc['file_path'])
            except Exception as e:
                logger.debug(f'Failed to load processed files from previous session: {e}')

        # Start subprocess
        cmd = [
            sys.executable, "-m", "whatsapp.monitor_worker",
            "--results", str(RESULTS_FILE),
            "--chats", str(self.chat_limit),
            "--interval", str(self.check_interval),
            "--session", self.session_dir,
            "--downloads", self.downloads_dir,
            "--timeout", "120"
        ]

        logger.info(f"Starting monitor subprocess: {' '.join(cmd)}")

        try:
            # Безопасно: cmd формируется из sys.executable и фиксированных аргументов
            self._process = subprocess.Popen(  # noqa: S603
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(Path(__file__).parent.parent)
            )
            logger.info(f"Monitor subprocess started (PID: {self._process.pid})")
            return True
        except Exception as e:
            logger.error(f"Failed to start monitor: {e}")
            return False

    def stop(self):
        """Stop the monitoring subprocess."""
        if self._process:
            logger.info("Stopping monitor subprocess...")
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception:
                with contextlib.suppress(Exception):
                    self._process.kill()
            self._process = None
            logger.info("Monitor subprocess stopped")

    def add_processed_file(self, file_path: str):
        """Mark file as already processed."""
        self._processed_files.add(file_path)

    def get_new_documents(self) -> list[dict]:
        """Get new documents from results file."""
        if not RESULTS_FILE.exists():
            return []

        try:
            data = json.loads(RESULTS_FILE.read_text(encoding='utf-8'))
            documents = data.get('documents', [])

            # Update stats from worker
            worker_stats = data.get('stats', {})
            self.stats['checks_count'] = worker_stats.get('checks', 0)
            if worker_stats.get('last_check'):
                with contextlib.suppress(Exception):
                    self.stats['last_check'] = datetime.fromisoformat(worker_stats['last_check'])
            self.stats['errors'] = worker_stats.get('errors', 0)

            # Find new documents
            new_docs = []
            for doc in documents:
                file_path = doc.get('file_path', '')
                if file_path and file_path not in self._processed_files:
                    self._processed_files.add(file_path)
                    new_docs.append(doc)
                    self.stats['documents_found'] += 1

            return new_docs

        except Exception as e:
            logger.error(f"Error reading results: {e}")
            return []

    def get_status(self) -> str:
        """Get current monitor status."""
        if not self.is_running:
            return "stopped"

        if not RESULTS_FILE.exists():
            return "starting"

        try:
            data = json.loads(RESULTS_FILE.read_text(encoding='utf-8'))
            status = data.get('status', 'unknown')
            return str(status) if status else 'unknown'
        except Exception:
            return "unknown"

    def read_subprocess_output(self) -> list[str]:
        """Read recent output from subprocess (non-blocking)."""
        lines = []
        if self._process and self._process.stdout:
            try:
                # Non-blocking read on Windows is tricky, just try readline
                while True:
                    line = self._process.stdout.readline()
                    if not line:
                        break
                    lines.append(line.strip())
            except Exception as e:
                logger.debug(f'Failed to load processed files from previous session: {e}')
        return lines


# Singleton instance
_monitor_instance: WhatsAppMonitor | None = None


def get_monitor() -> WhatsAppMonitor | None:
    """Get the global monitor instance."""
    return _monitor_instance


def create_monitor(**kwargs) -> WhatsAppMonitor:
    """Create or get the global monitor instance."""
    global _monitor_instance
    if _monitor_instance is None:
        _monitor_instance = WhatsAppMonitor(**kwargs)
    return _monitor_instance


def stop_monitor():
    """Stop and clear the global monitor."""
    global _monitor_instance
    if _monitor_instance:
        _monitor_instance.stop()
        _monitor_instance = None
