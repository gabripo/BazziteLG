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
    inp.write_text("HDMI_3\n")
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
    assert status["tv_input"] == "HDMI_3"
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
        res = await plugin.power_on("HDMI_2")

    assert res["success"] is True
    assert "OK" in res["output"]
    args = mock_exec.call_args[0]
    assert "on" in args
    assert "HDMI_2" in args


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


async def test_power_commands_use_system_python_not_loader(plugin, monkeypatch):
    # Inside Decky, sys.executable is the frozen PluginLoader binary
    monkeypatch.setattr(sys, "executable", "/home/deck/homebrew/services/PluginLoader")
    mock_proc = MagicMock()
    mock_proc.communicate = AsyncMock(return_value=(b"", b""))
    mock_proc.returncode = 0

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)) as mock_exec:
        await plugin.power_off()

    assert "PluginLoader" not in mock_exec.call_args[0][0]
    assert mock_exec.call_args[0][0].endswith("python3")


async def test_power_commands_strip_pyinstaller_lib_path(plugin, monkeypatch):
    monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/_MEI12345")
    monkeypatch.delenv("LD_LIBRARY_PATH_ORIG", raising=False)
    mock_proc = MagicMock()
    mock_proc.communicate = AsyncMock(return_value=(b"", b""))
    mock_proc.returncode = 0

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)) as mock_exec:
        await plugin.power_on()

    assert "LD_LIBRARY_PATH" not in mock_exec.call_args.kwargs["env"]


def test_clean_env_restores_original_lib_path(monkeypatch):
    monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/_MEI12345")
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/opt/lib")
    env = decky_main._clean_env()
    assert env["LD_LIBRARY_PATH"] == "/opt/lib"
    assert "LD_LIBRARY_PATH_ORIG" not in env


# ── frontend bundle ───────────────────────────────────────────────────────────

_PLUGIN_DIR = _PLUGIN_PATH.parent
_BUNDLE = (_PLUGIN_DIR / "dist" / "index.js").read_text()


def test_bundle_has_no_bare_imports():
    # Decky's CEF context cannot resolve npm specifiers; React/@decky/ui are globals
    import re
    assert not re.search(r"^\s*import\s", _BUNDLE, re.MULTILINE)
    assert "SP_REACT" in _BUNDLE and "DFL" in _BUNDLE
    assert "export { index as default }" in _BUNDLE


def test_bundle_api_version_matches_manifest():
    import json, re
    manifest = json.loads((_PLUGIN_DIR / "plugin.json").read_text())
    m = re.search(r"const API_VERSION = (\d+);", _BUNDLE)
    assert m and int(m.group(1)) == manifest["api_version"]
    assert "callPluginMethod" not in _BUNDLE   # legacy (api_version 0) API


def test_bundle_calls_only_existing_backend_methods():
    import re
    called = set(re.findall(r'call\("(\w+)"', _BUNDLE))
    called |= set(re.findall(r'"(power_on|power_off)"', _BUNDLE))
    assert called, "no backend calls found in bundle"
    for name in called:
        assert callable(getattr(decky_main.Plugin, name, None)), name
