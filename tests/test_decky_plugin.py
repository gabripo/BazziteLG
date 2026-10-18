"""Unit tests for decky-plugin/main.py."""

import asyncio
import importlib.util
import pathlib
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Load decky-plugin/main.py dynamically
_PLUGIN_PATH = pathlib.Path(__file__).parent.parent / "decky-plugin" / "main.py"
spec = importlib.util.spec_from_file_location("decky_main", _PLUGIN_PATH)
decky_main = importlib.util.module_from_spec(spec)
spec.loader.exec_module(decky_main)


@pytest.fixture
def plugin():
    return decky_main.Plugin()


async def test_get_status_active(plugin, tmp_path):
    ip = tmp_path / "tv_ip"
    ip.write_text("192.168.1.55\n")
    mac = tmp_path / "tv_mac"
    mac.write_text("aa:bb:cc:dd:ee:ff\n")
    inp = tmp_path / "tv_input"
    inp.write_text("HDMI3\n")
    key = tmp_path / "client.key"
    key.write_text("secret-key\n")
    disabled = tmp_path / "disabled"

    with patch.object(decky_main, "IP_FILE", ip), \
         patch.object(decky_main, "MAC_FILE", mac), \
         patch.object(decky_main, "INPUT_FILE", inp), \
         patch.object(decky_main, "KEY_FILE", key), \
         patch.object(decky_main, "DISABLED_FILE", disabled):
        status = await plugin.get_status()

    assert status["sync_enabled"] is True
    assert status["status_text"] == "ACTIVATED"
    assert status["tv_ip"] == "192.168.1.55"
    assert status["tv_mac"] == "aa:bb:cc:dd:ee:ff"
    assert status["tv_input"] == "HDMI3"
    assert status["paired"] is True


async def test_get_status_disabled(plugin, tmp_path):
    disabled = tmp_path / "disabled"
    disabled.touch()

    with patch.object(decky_main, "DISABLED_FILE", disabled), \
         patch.object(decky_main, "IP_FILE", tmp_path / "tv_ip"), \
         patch.object(decky_main, "MAC_FILE", tmp_path / "tv_mac"), \
         patch.object(decky_main, "INPUT_FILE", tmp_path / "tv_input"), \
         patch.object(decky_main, "KEY_FILE", tmp_path / "client.key"):
        status = await plugin.get_status()

    assert status["sync_enabled"] is False
    assert status["status_text"] == "DEACTIVATED"


async def test_set_sync_disable_and_enable(plugin, tmp_path):
    disabled = tmp_path / "disabled"
    with patch.object(decky_main, "DISABLED_FILE", disabled):
        res1 = await plugin.set_sync(False)
        assert res1["success"] is True
        assert res1["sync_enabled"] is False
        assert disabled.exists()

        res2 = await plugin.set_sync(True)
        assert res2["success"] is True
        assert res2["sync_enabled"] is True
        assert not disabled.exists()


async def test_toggle_sync(plugin, tmp_path):
    disabled = tmp_path / "disabled"
    with patch.object(decky_main, "DISABLED_FILE", disabled):
        res1 = await plugin.toggle_sync()
        assert res1["sync_enabled"] is False
        assert disabled.exists()

        res2 = await plugin.toggle_sync()
        assert res2["sync_enabled"] is True
        assert not disabled.exists()


async def test_power_on_executes_script(plugin):
    mock_proc = MagicMock()
    mock_proc.communicate = AsyncMock(return_value=(b"OK\n", b""))
    mock_proc.returncode = 0

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)) as mock_exec:
        res = await plugin.power_on("HDMI2")

    assert res["success"] is True
    assert "OK" in res["output"]
    args = mock_exec.call_args[0]
    assert "on" in args
    assert "HDMI2" in args


async def test_power_off_executes_script(plugin):
    mock_proc = MagicMock()
    mock_proc.communicate = AsyncMock(return_value=(b"Done\n", b""))
    mock_proc.returncode = 0

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)) as mock_exec:
        res = await plugin.power_off()

    assert res["success"] is True
    assert "Done" in res["output"]
    args = mock_exec.call_args[0]
    assert "off" in args
