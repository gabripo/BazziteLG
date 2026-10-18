#!/usr/bin/env python3
"""Backend for Decky Loader LG TV Control Plugin."""

import asyncio
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Decky logger support
try:
    import decky
    logger = decky.logger
except ImportError:
    try:
        import decky_plugin
        logger = decky_plugin.logger
    except ImportError:
        import logging
        logger = logging.getLogger("bazzite-lgtv")
        logger.setLevel(logging.INFO)

CONF_DIR = Path("/etc/lgtvcontrol")
LGTV_PY = CONF_DIR / "lgtv.py"
DISABLED_FILE = CONF_DIR / "disabled"
IP_FILE = CONF_DIR / "tv_ip"
INPUT_FILE = CONF_DIR / "tv_input"
MAC_FILE = CONF_DIR / "tv_mac"
KEY_FILE = CONF_DIR / "client.key"


def _read_file(p: Path) -> str:
    try:
        return p.read_text().strip() if p.exists() else ""
    except Exception:
        return ""


class Plugin:
    async def _main(self):
        logger.info("BazziteLG Decky Plugin initialized")

    async def _unload(self):
        logger.info("BazziteLG Decky Plugin unloaded")

    async def get_status(self) -> dict:
        disabled = DISABLED_FILE.exists()
        return {
            "sync_enabled": not disabled,
            "status_text": "DEACTIVATED" if disabled else "ACTIVATED",
            "tv_ip": _read_file(IP_FILE),
            "tv_mac": _read_file(MAC_FILE),
            "tv_input": _read_file(INPUT_FILE),
            "paired": KEY_FILE.exists(),
        }

    async def toggle_sync(self) -> dict:
        disabled = DISABLED_FILE.exists()
        return await self.set_sync(disabled)

    async def set_sync(self, enabled: bool) -> dict:
        try:
            if enabled:
                DISABLED_FILE.unlink(missing_ok=True)
            else:
                DISABLED_FILE.touch()
                try:
                    DISABLED_FILE.chmod(0o666)
                except OSError:
                    pass
        except PermissionError as e:
            logger.error(f"Permission denied modifying {DISABLED_FILE}: {e}")
            return {"success": False, "error": f"Permission denied: {e}"}
        except Exception as e:
            logger.error(f"Error toggling sync: {e}")
            return {"success": False, "error": str(e)}

        return {"success": True, "sync_enabled": not DISABLED_FILE.exists()}

    async def power_on(self, input_id: str = "") -> dict:
        script = LGTV_PY if LGTV_PY.exists() else Path(__file__).parent.parent / "scripts" / "lgtv.py"
        cmd = [sys.executable, str(script), "on"]
        if input_id:
            cmd.append(input_id)
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            out = (stdout.decode() + stderr.decode()).strip()
            return {"success": proc.returncode == 0, "output": out}
        except Exception as e:
            logger.error(f"power_on error: {e}")
            return {"success": False, "output": str(e)}

    async def power_off(self) -> dict:
        script = LGTV_PY if LGTV_PY.exists() else Path(__file__).parent.parent / "scripts" / "lgtv.py"
        cmd = [sys.executable, str(script), "off"]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            out = (stdout.decode() + stderr.decode()).strip()
            return {"success": proc.returncode == 0, "output": out}
        except Exception as e:
            logger.error(f"power_off error: {e}")
            return {"success": False, "output": str(e)}

    async def test_screen(self) -> dict:
        async def _run_test():
            await self.power_off()
            await asyncio.sleep(10)
            await self.power_on()

        asyncio.create_task(_run_test())
        return {"success": True, "message": "Screen test initiated (off 10s → on)"}
