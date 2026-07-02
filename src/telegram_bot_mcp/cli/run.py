"""Mode dispatch: polling, webhook, MCP-only, or combined."""

import argparse
import asyncio
import logging
import signal
import socket
import subprocess
import sys
from types import FrameType

from ..config import AppConfig, load_config
from .args import build_parser
from .preflight import check_configuration

logger = logging.getLogger(__name__)

FULL_EXTRA_HINT = (
    "This mode needs the optional dependencies. Install them with: "
    "uv sync --extra full  (or: pip install '.[full]')"
)
MCP_READY_TIMEOUT_SECONDS = 10.0
MCP_READY_POLL_SECONDS = 0.25
PROCESS_STOP_TIMEOUT_SECONDS = 5.0


class StartupManager:
    """Tracks spawned subprocesses and guarantees their cleanup."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.processes: list[subprocess.Popen[str]] = []

    def start_mcp_subprocess(self) -> subprocess.Popen[str]:
        """Run the MCP server as a child process."""
        cmd = [
            sys.executable,
            "-m",
            "telegram_bot_mcp.mcp",
            "--host",
            self.config.server.host,
            "--port",
            str(self.config.server.mcp_port),
        ]
        process = subprocess.Popen(cmd, text=True)
        self.processes.append(process)
        logger.info("MCP server started with PID %d", process.pid)
        return process

    async def _await_mcp_ready(self, process: subprocess.Popen[str]) -> None:
        """Block until the MCP port accepts connections, or the process dies."""
        deadline = asyncio.get_running_loop().time() + MCP_READY_TIMEOUT_SECONDS
        while asyncio.get_running_loop().time() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"MCP server exited early with code {process.returncode}")
            if self._port_open("127.0.0.1", self.config.server.mcp_port):
                logger.info("MCP server is accepting connections")
                return
            await asyncio.sleep(MCP_READY_POLL_SECONDS)
        logger.warning("MCP server not ready after %.0fs; continuing", MCP_READY_TIMEOUT_SECONDS)

    @staticmethod
    def _port_open(host: str, port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            return sock.connect_ex((host, port)) == 0

    async def run_polling(self) -> None:
        from ..bot import BotRunner

        runner = BotRunner()
        await runner.initialize()
        await runner.start_polling()

    async def run_webhook(self) -> None:
        import uvicorn

        if not self.config.telegram.webhook_url:
            raise ValueError("TELEGRAM_WEBHOOK_URL must be set for webhook mode")
        if self.config.server.debug:
            logger.info("Debug mode on; auto-reload is not available under this launcher")

        uvicorn_config = uvicorn.Config(
            "telegram_bot_mcp.webhook:app",
            host=self.config.server.host,
            port=self.config.server.port,
            log_level=self.config.server.log_level.lower(),
        )
        await uvicorn.Server(uvicorn_config).serve()

    async def run_combined(self) -> None:
        process = self.start_mcp_subprocess()
        try:
            await self._await_mcp_ready(process)
            await self.run_webhook()
        finally:
            self.cleanup_processes()

    def cleanup_processes(self) -> None:
        for process in self.processes:
            if process.poll() is None:
                logger.info("Terminating process %d", process.pid)
                process.terminate()
                try:
                    process.wait(timeout=PROCESS_STOP_TIMEOUT_SECONDS)
                except subprocess.TimeoutExpired:
                    logger.warning("Force killing process %d", process.pid)
                    process.kill()
        self.processes.clear()


def _install_sigterm_handler() -> None:
    """Turn SIGTERM (e.g. `docker stop`) into KeyboardInterrupt.

    Both SIGINT and SIGTERM then unwind through the same except/finally path,
    so graceful shutdown and subprocess cleanup run for either signal.
    """

    def handle_sigterm(signum: int, frame: FrameType | None) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, handle_sigterm)


def _apply_overrides(config: AppConfig, args: argparse.Namespace) -> None:
    if args.host is not None:
        config.server.host = args.host
    if args.port is not None:
        config.server.port = args.port
    if args.mcp_port is not None:
        config.server.mcp_port = args.mcp_port
    if args.debug:
        config.server.debug = True
    if args.log_level is not None:
        config.server.log_level = args.log_level


def main() -> None:
    args = build_parser().parse_args()

    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=getattr(logging, args.log_level or "INFO"),
    )

    if args.check_config:
        ok, report = check_configuration()
        print(report)
        sys.exit(0 if ok else 1)

    try:
        config = load_config()
    except ValueError as exc:
        logger.error("Configuration error: %s", exc)
        sys.exit(1)
    _apply_overrides(config, args)
    logging.getLogger().setLevel(getattr(logging, config.server.log_level))

    _install_sigterm_handler()
    manager = StartupManager(config)

    try:
        if args.mcp:
            from ..mcp import run as run_mcp

            run_mcp(host=config.server.host, port=config.server.mcp_port)
        elif args.webhook:
            asyncio.run(manager.run_webhook())
        elif args.combined:
            asyncio.run(manager.run_combined())
        else:
            asyncio.run(manager.run_polling())
    except KeyboardInterrupt:
        logger.info("Shutdown requested")
    except ImportError as exc:
        logger.error("Missing dependency: %s. %s", exc.name, FULL_EXTRA_HINT)
        sys.exit(1)
    except ValueError as exc:
        logger.error("Startup error: %s", exc)
        sys.exit(1)
    finally:
        manager.cleanup_processes()
