import os
import sys
import uuid
import socket
import logging
import asyncio
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

class JupyterManager:
    """Manages a background persistent Jupyter Server for Sphinx orchestrations."""

    def __init__(self, root_dir: str):
        self.root_dir = root_dir
        self.process: Optional[subprocess.Popen] = None
        self.port: Optional[int] = None
        self.token: str = uuid.uuid4().hex
        self.url: Optional[str] = None

    def _find_free_port(self) -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            return s.getsockname()[1]

    async def start(self):
        """Starts the Jupyter Server in the background."""
        if self.process is not None:
            logger.warning("Jupyter Server is already running.")
            return

        self.port = self._find_free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        
        cmd = [
            sys.executable,
            "-m", "jupyter", "server",
            "--no-browser",
            f"--port={self.port}",
            f"--IdentityProvider.token={self.token}",
            f"--ServerApp.log_level=ERROR",
            f"--ServerApp.root_dir={self.root_dir}",
            "--ServerApp.disable_check_xsrf=True", # Useful for API calls
        ]

        logger.info(f"Starting persistent Jupyter Server for Sphinx on port {self.port}...")
        
        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=self.root_dir
        )

        # Give it a few seconds to fully bind
        for _ in range(10):
            try:
                reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
                writer.close()
                await writer.wait_closed()
                logger.info(f"✓ Persistent Jupyter Server is ready at {self.url}")
                return
            except ConnectionRefusedError:
                await asyncio.sleep(0.5)
                
        logger.error("Failed to connect to the persistent Jupyter Server after 5 seconds.")

    def stop(self):
        """Stops the Jupyter Server."""
        if self.process:
            logger.info("Stopping persistent Jupyter Server...")
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None
            self.port = None
            self.url = None
