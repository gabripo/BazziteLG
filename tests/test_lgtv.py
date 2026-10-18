"""Unit tests for scripts/lgtv.py"""

import asyncio
import json
import pathlib
import struct
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import lgtv
from lgtv import WebSocket, run, ws_connect


@pytest.fixture
def no_retries(monkeypatch):
    """Collapse retry loop to a single attempt so error-path tests exit fast."""
    monkeypatch.setattr(lgtv, "RETRY_ATTEMPTS", 1)


# ── helpers ───────────────────────────────────────────────────────────────────

def server_frame(payload: bytes | str, opcode: int = 1) -> bytes:
    """Build an unmasked server→client WebSocket frame."""
    if isinstance(payload, str):
        payload = payload.encode()
    n = len(payload)
    if n < 126:
        return bytes([0x80 | opcode, n]) + payload
    if n < 65536:
        return bytes([0x80 | opcode, 126]) + struct.pack(">H", n) + payload
    return bytes([0x80 | opcode, 127]) + struct.pack(">Q", n) + payload


def make_reader(data: bytes) -> asyncio.StreamReader:
    r = asyncio.StreamReader()
    r.feed_data(data)
    return r


def make_writer() -> MagicMock:
    w = MagicMock()
    w.write = MagicMock()
    w.drain = AsyncMock()
    w.close = MagicMock()
    w.wait_closed = AsyncMock()
    return w


def make_ws(*messages) -> MagicMock:
    ws = MagicMock(spec=WebSocket)
    ws.send = AsyncMock()
    ws.recv = AsyncMock(side_effect=list(messages))
    ws.close = AsyncMock()
    return ws


def setup_files(tmp_path, client_key="stored-key"):
    ip = tmp_path / "tv_ip"
    ip.write_text("192.168.1.100\n")
    key = tmp_path / "client.key"
    key.write_text(client_key + "\n")
    return ip, key


# ── canned TV messages ────────────────────────────────────────────────────────

REGISTERED = json.dumps({"type": "registered", "payload": {"client-key": "test-key-123"}})
PROMPT     = json.dumps({"type": "response",   "payload": {"pairingType": "PROMPT"}})
SUCCESS    = json.dumps({"type": "response",   "payload": {"returnValue": True}})
ERROR      = json.dumps({"type": "error",      "payload": {"errorCode": "-500", "errorText": "fail"}})
ALREADY    = json.dumps({"type": "error",      "payload": {"errorCode": "-102"}})
BLACKLIST  = json.dumps({"type": "error", "id": "register_0", "payload": {},
                         "error": "403 Pairing rejected: blacklisted certificate detected"})


# ── WebSocket.send ────────────────────────────────────────────────────────────

async def test_send_small_payload():
    ws = WebSocket(asyncio.StreamReader(), make_writer())
    await ws.send("hello")
    data = ws._w.write.call_args[0][0]
    assert data[0] == 0x81          # FIN + text opcode
    assert data[1] == 0x80 | 5      # masked, length=5
    mask = data[2:6]
    assert bytes(b ^ mask[i % 4] for i, b in enumerate(data[6:])) == b"hello"


async def test_send_medium_payload():
    ws = WebSocket(asyncio.StreamReader(), make_writer())
    await ws.send("x" * 200)
    data = ws._w.write.call_args[0][0]
    assert data[1] == 0xFE                               # masked + 16-bit length
    assert struct.unpack(">H", data[2:4])[0] == 200


async def test_send_large_payload():
    ws = WebSocket(asyncio.StreamReader(), make_writer())
    await ws.send("x" * 70000)
    data = ws._w.write.call_args[0][0]
    assert data[1] == 0xFF                               # masked + 64-bit length
    assert struct.unpack(">Q", data[2:10])[0] == 70000


# ── WebSocket.recv ────────────────────────────────────────────────────────────

async def test_recv_small_frame():
    ws = WebSocket(make_reader(server_frame("hello")), make_writer())
    assert await ws.recv() == "hello"


async def test_recv_medium_frame():
    payload = "x" * 200
    ws = WebSocket(make_reader(server_frame(payload)), make_writer())
    assert await ws.recv() == payload


async def test_recv_large_frame():
    payload = "x" * 70000
    ws = WebSocket(make_reader(server_frame(payload)), make_writer())
    assert await ws.recv() == payload


async def test_recv_close_frame_raises():
    ws = WebSocket(make_reader(server_frame(b"", opcode=8)), make_writer())
    with pytest.raises(ConnectionError, match="Server closed"):
        await ws.recv()


# ── WebSocket.close ───────────────────────────────────────────────────────────

async def test_close_sends_close_frame():
    writer = make_writer()
    ws = WebSocket(asyncio.StreamReader(), writer)
    await ws.close()
    assert writer.write.call_args[0][0][0] == 0x88   # FIN + close opcode
    writer.close.assert_called_once()


# ── ws_connect ────────────────────────────────────────────────────────────────

async def test_ws_connect_success():
    resp = b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n\r\n"
    with patch("asyncio.open_connection", return_value=(make_reader(resp), make_writer())):
        ws = await ws_connect("192.168.1.1", 3001, MagicMock())
    assert isinstance(ws, WebSocket)
    written = ws._w.write.call_args[0][0].decode()
    assert "Upgrade: websocket" in written
    assert "Sec-WebSocket-Key" in written


async def test_ws_connect_bad_status():
    resp = b"HTTP/1.1 403 Forbidden\r\n\r\n"
    with patch("asyncio.open_connection", return_value=(make_reader(resp), make_writer())):
        with pytest.raises(ConnectionError, match="WebSocket upgrade failed"):
            await ws_connect("192.168.1.1", 3001, MagicMock())


# ── run() — pair ──────────────────────────────────────────────────────────────

async def test_pair_saves_key(tmp_path):
    ip = tmp_path / "tv_ip"
    ip.write_text("192.168.1.100\n")
    key = tmp_path / "client.key"
    ws = make_ws(PROMPT, REGISTERED)
    with patch.object(lgtv, "IP_FILE", ip), patch.object(lgtv, "KEY_FILE", key), \
         patch("lgtv.ws_connect", AsyncMock(return_value=ws)):
        await run("pair")
    assert key.read_text().strip() == "test-key-123"


async def test_pair_prompts_user(tmp_path, capsys):
    ip = tmp_path / "tv_ip"
    ip.write_text("192.168.1.100\n")
    key = tmp_path / "client.key"
    ws = make_ws(PROMPT, REGISTERED)
    with patch.object(lgtv, "IP_FILE", ip), patch.object(lgtv, "KEY_FILE", key), \
         patch("lgtv.ws_connect", AsyncMock(return_value=ws)):
        await run("pair")
    assert "Approve" in capsys.readouterr().out


async def test_pair_falls_back_to_unsigned_manifest(tmp_path):
    ip = tmp_path / "tv_ip"
    ip.write_text("192.168.1.100\n")
    key = tmp_path / "client.key"
    ws = make_ws(BLACKLIST, PROMPT, REGISTERED)
    with patch.object(lgtv, "IP_FILE", ip), patch.object(lgtv, "KEY_FILE", key), \
         patch("lgtv.ws_connect", AsyncMock(return_value=ws)):
        await run("pair")
    first, second = (json.loads(c.args[0])["payload"]["manifest"] for c in ws.send.call_args_list[:2])
    assert "signatures" in first
    assert "signatures" not in second and "signed" not in second
    assert key.read_text().strip() == "test-key-123"


async def test_on_falls_back_to_unsigned_manifest(tmp_path):
    ip, key = setup_files(tmp_path)
    ws = make_ws(BLACKLIST, REGISTERED, SUCCESS)
    with patch.object(lgtv, "IP_FILE", ip), patch.object(lgtv, "KEY_FILE", key), \
         patch("lgtv.ws_connect", AsyncMock(return_value=ws)):
        await run("on")
    cmd = json.loads(ws.send.call_args_list[2].args[0])
    assert cmd["uri"] == "ssap://com.webos.service.tvpower/power/turnOnScreen"


# ── run() — on/off ────────────────────────────────────────────────────────────

async def test_on_uri_and_payload(tmp_path):
    ip, key = setup_files(tmp_path)
    ws = make_ws(REGISTERED, SUCCESS)
    with patch.object(lgtv, "IP_FILE", ip), patch.object(lgtv, "KEY_FILE", key), \
         patch("lgtv.ws_connect", AsyncMock(return_value=ws)):
        await run("on")
    cmd = json.loads(ws.send.call_args_list[1].args[0])
    assert cmd["uri"] == "ssap://com.webos.service.tvpower/power/turnOnScreen"
    assert cmd["payload"] == {}


async def test_off_uri_and_payload(tmp_path):
    ip, key = setup_files(tmp_path)
    ws = make_ws(REGISTERED, SUCCESS)
    with patch.object(lgtv, "IP_FILE", ip), patch.object(lgtv, "KEY_FILE", key), \
         patch("lgtv.ws_connect", AsyncMock(return_value=ws)):
        await run("off")
    cmd = json.loads(ws.send.call_args_list[1].args[0])
    assert cmd["uri"] == "ssap://system/turnOff"
    assert cmd["payload"] == {"standbyMode": "active"}


async def test_sends_stored_client_key(tmp_path):
    ip, key = setup_files(tmp_path, "my-client-key")
    ws = make_ws(REGISTERED, SUCCESS)
    with patch.object(lgtv, "IP_FILE", ip), patch.object(lgtv, "KEY_FILE", key), \
         patch("lgtv.ws_connect", AsyncMock(return_value=ws)):
        await run("on")
    reg = json.loads(ws.send.call_args_list[0].args[0])
    assert reg["payload"]["client-key"] == "my-client-key"


async def test_error_102_not_fatal(tmp_path):
    """errorCode -102 means screen already in desired state — not an error."""
    ip, key = setup_files(tmp_path)
    ws = make_ws(REGISTERED, ALREADY)
    with patch.object(lgtv, "IP_FILE", ip), patch.object(lgtv, "KEY_FILE", key), \
         patch("lgtv.ws_connect", AsyncMock(return_value=ws)):
        await run("on")   # must not raise


async def test_command_error_exits(tmp_path):
    ip, key = setup_files(tmp_path)
    ws = make_ws(REGISTERED, ERROR)
    with patch.object(lgtv, "IP_FILE", ip), patch.object(lgtv, "KEY_FILE", key), \
         patch("lgtv.ws_connect", AsyncMock(return_value=ws)):
        with pytest.raises(SystemExit):
            await run("on")


async def test_registration_error_exits(tmp_path):
    ip, key = setup_files(tmp_path)
    ws = make_ws(ERROR)
    with patch.object(lgtv, "IP_FILE", ip), patch.object(lgtv, "KEY_FILE", key), \
         patch("lgtv.ws_connect", AsyncMock(return_value=ws)):
        with pytest.raises(SystemExit):
            await run("on")


# ── run() — HDMI input switching ─────────────────────────────────────────────

async def test_on_without_input_no_switch(tmp_path):
    ip, key = setup_files(tmp_path)
    input_file = tmp_path / "tv_input"          # not created
    ws = make_ws(REGISTERED, SUCCESS)
    with patch.object(lgtv, "IP_FILE", ip), patch.object(lgtv, "KEY_FILE", key), \
         patch.object(lgtv, "INPUT_FILE", input_file), \
         patch("lgtv.ws_connect", AsyncMock(return_value=ws)):
        await run("on")
    assert ws.send.call_count == 2   # register + turnOnScreen only


async def test_on_uses_configured_input(tmp_path):
    ip, key = setup_files(tmp_path)
    input_file = tmp_path / "tv_input"
    input_file.write_text("HDMI_3\n")
    ws = make_ws(REGISTERED, SUCCESS, SUCCESS)
    with patch.object(lgtv, "IP_FILE", ip), patch.object(lgtv, "KEY_FILE", key), \
         patch.object(lgtv, "INPUT_FILE", input_file), \
         patch.object(lgtv, "INPUT_SWITCH_DELAY", 0), \
         patch("lgtv.ws_connect", AsyncMock(return_value=ws)):
        await run("on")
    switch = json.loads(ws.send.call_args_list[2].args[0])
    assert switch["uri"] == "ssap://tv/switchInput"
    assert switch["payload"] == {"inputId": "HDMI_3"}


async def test_on_cli_arg_overrides_config(tmp_path):
    ip, key = setup_files(tmp_path)
    input_file = tmp_path / "tv_input"
    input_file.write_text("HDMI_3\n")
    ws = make_ws(REGISTERED, SUCCESS, SUCCESS)
    with patch.object(lgtv, "IP_FILE", ip), patch.object(lgtv, "KEY_FILE", key), \
         patch.object(lgtv, "INPUT_FILE", input_file), \
         patch.object(lgtv, "INPUT_SWITCH_DELAY", 0), \
         patch("lgtv.ws_connect", AsyncMock(return_value=ws)):
        await run("on", "HDMI_2")
    switch = json.loads(ws.send.call_args_list[2].args[0])
    assert switch["payload"] == {"inputId": "HDMI_2"}


async def test_switch_input_102_not_fatal(tmp_path):
    """Input switch errorCode -102 (already on that input) is not an error."""
    ip, key = setup_files(tmp_path)
    ws = make_ws(REGISTERED, SUCCESS, ALREADY)
    with patch.object(lgtv, "IP_FILE", ip), patch.object(lgtv, "KEY_FILE", key), \
         patch.object(lgtv, "INPUT_SWITCH_DELAY", 0), \
         patch("lgtv.ws_connect", AsyncMock(return_value=ws)):
        await run("on", "HDMI_3")   # must not raise


async def test_switch_input_error_exits(tmp_path):
    ip, key = setup_files(tmp_path)
    ws = make_ws(REGISTERED, SUCCESS, ERROR)
    with patch.object(lgtv, "IP_FILE", ip), patch.object(lgtv, "KEY_FILE", key), \
         patch.object(lgtv, "INPUT_SWITCH_DELAY", 0), \
         patch("lgtv.ws_connect", AsyncMock(return_value=ws)):
        with pytest.raises(SystemExit, match="Input switch failed"):
            await run("on", "HDMI_3")


# ── run() — missing files ─────────────────────────────────────────────────────

async def test_missing_ip_exits(tmp_path):
    ip = tmp_path / "tv_ip"          # not created
    key = tmp_path / "client.key"
    key.write_text("key\n")
    with patch.object(lgtv, "IP_FILE", ip), patch.object(lgtv, "KEY_FILE", key):
        with pytest.raises(SystemExit, match="TV IP not configured"):
            await run("on")


async def test_missing_key_exits(tmp_path):
    ip = tmp_path / "tv_ip"
    ip.write_text("192.168.1.100\n")
    key = tmp_path / "client.key"    # not created
    with patch.object(lgtv, "IP_FILE", ip), patch.object(lgtv, "KEY_FILE", key):
        with pytest.raises(SystemExit, match="No client key"):
            await run("on")


# ── run() — connection failures ───────────────────────────────────────────────

async def test_connect_timeout_exits(tmp_path, no_retries):
    ip, key = setup_files(tmp_path)
    with patch.object(lgtv, "IP_FILE", ip), patch.object(lgtv, "KEY_FILE", key), \
         patch("lgtv.ws_connect", AsyncMock(side_effect=asyncio.TimeoutError())):
        with pytest.raises(SystemExit, match="Could not reach TV"):
            await run("on")


async def test_connect_os_error_exits(tmp_path, no_retries):
    ip, key = setup_files(tmp_path)
    with patch.object(lgtv, "IP_FILE", ip), patch.object(lgtv, "KEY_FILE", key), \
         patch("lgtv.ws_connect", AsyncMock(side_effect=OSError("refused"))):
        with pytest.raises(SystemExit, match="Could not reach TV"):
            await run("on")


# ── run() — retry logic ───────────────────────────────────────────────────────

async def test_retries_on_connection_drop(tmp_path, monkeypatch):
    """TV closes the WebSocket during registration; script retries and succeeds."""
    monkeypatch.setattr(lgtv, "RETRY_DELAY", 0)
    ip, key = setup_files(tmp_path)
    ws_drop = make_ws(ConnectionError("Server closed the WebSocket connection"))
    ws_ok   = make_ws(REGISTERED, SUCCESS)
    with patch.object(lgtv, "IP_FILE", ip), patch.object(lgtv, "KEY_FILE", key), \
         patch("lgtv.ws_connect", AsyncMock(side_effect=[ws_drop, ws_ok])):
        await run("on")   # must not raise
    cmd = json.loads(ws_ok.send.call_args_list[1].args[0])
    assert cmd["uri"] == "ssap://com.webos.service.tvpower/power/turnOnScreen"


async def test_retries_on_connect_error_then_succeeds(tmp_path, monkeypatch):
    """TCP connection refused on first attempt; second attempt succeeds."""
    monkeypatch.setattr(lgtv, "RETRY_DELAY", 0)
    ip, key = setup_files(tmp_path)
    ws_ok = make_ws(REGISTERED, SUCCESS)
    with patch.object(lgtv, "IP_FILE", ip), patch.object(lgtv, "KEY_FILE", key), \
         patch("lgtv.ws_connect", AsyncMock(side_effect=[OSError("refused"), ws_ok])):
        await run("on")   # must not raise


async def test_exhausts_retries_and_exits(tmp_path, monkeypatch):
    """Every attempt fails; script exits after RETRY_ATTEMPTS attempts."""
    monkeypatch.setattr(lgtv, "RETRY_ATTEMPTS", 3)
    monkeypatch.setattr(lgtv, "RETRY_DELAY", 0)
    ip, key = setup_files(tmp_path)
    # side_effect as a bare exception (not a list) means it fires on every call
    ws_drop = MagicMock(spec=WebSocket)
    ws_drop.send = AsyncMock()
    ws_drop.recv = AsyncMock(side_effect=ConnectionError("Server closed the WebSocket connection"))
    ws_drop.close = AsyncMock()
    mock_connect = AsyncMock(return_value=ws_drop)
    with patch.object(lgtv, "IP_FILE", ip), patch.object(lgtv, "KEY_FILE", key), \
         patch("lgtv.ws_connect", mock_connect):
        with pytest.raises(SystemExit, match="Could not reach TV"):
            await run("on")
    assert mock_connect.call_count == 3


# ── _subnet_broadcast ────────────────────────────────────────────────────────

def test_subnet_broadcast_detects_correct_address():
    """Returns directed broadcast for the interface that routes to tv_ip."""
    import struct, socket as _socket

    local_ip = "192.168.50.10"
    netmask   = "255.255.255.0"
    # expected broadcast: 192.168.50.255
    expected  = "192.168.50.255"

    def make_ifreq(ip: str) -> bytes:
        packed_ip = _socket.inet_aton(ip)
        return struct.pack("16sH2s4s8s", b"eth0\0" * 1, _socket.AF_INET, b"\0\0", packed_ip, b"\0" * 8)

    probe_sock = MagicMock()
    probe_sock.__enter__ = MagicMock(return_value=probe_sock)
    probe_sock.__exit__  = MagicMock(return_value=False)
    probe_sock.getsockname.return_value = (local_ip, 0)

    query_sock = MagicMock()
    query_sock.__enter__ = MagicMock(return_value=query_sock)
    query_sock.__exit__  = MagicMock(return_value=False)
    query_sock.fileno.return_value = 3

    with patch("socket.socket", side_effect=[probe_sock, query_sock, query_sock]), \
         patch("socket.if_nameindex", return_value=[(1, "eth0")]), \
         patch("fcntl.ioctl", side_effect=[make_ifreq(local_ip), make_ifreq(netmask)]):
        result = lgtv._subnet_broadcast("192.168.50.1")

    assert result == expected


def test_subnet_broadcast_falls_back_on_no_match():
    """Falls back to 255.255.255.255 when no interface matches the route."""
    probe_sock = MagicMock()
    probe_sock.__enter__ = MagicMock(return_value=probe_sock)
    probe_sock.__exit__  = MagicMock(return_value=False)
    probe_sock.getsockname.return_value = ("10.0.0.5", 0)

    with patch("socket.socket", return_value=probe_sock), \
         patch("socket.if_nameindex", return_value=[]), \
         patch("fcntl.ioctl", side_effect=OSError):
        result = lgtv._subnet_broadcast("10.0.0.1")

    assert result == "255.255.255.255"


# ── _send_wol ─────────────────────────────────────────────────────────────────

def test_send_wol_packet_structure():
    """Magic packet = 6×0xFF header + MAC repeated 16 times."""
    import socket as _socket
    with patch("lgtv._subnet_broadcast", return_value="192.168.1.255"), \
         patch("socket.socket") as mock_cls:
        sock = MagicMock()
        mock_cls.return_value.__enter__ = MagicMock(return_value=sock)
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)
        lgtv._send_wol("aa:bb:cc:dd:ee:ff", "192.168.1.100")
    packet = sock.sendto.call_args_list[0][0][0]
    assert packet[:6] == b"\xff" * 6
    assert packet[6:] == bytes.fromhex("aabbccddeeff") * 16
    sock.setsockopt.assert_called_once_with(_socket.SOL_SOCKET, _socket.SO_BROADCAST, 1)


def test_send_wol_normalises_separators():
    """MAC with dashes and mixed case is handled correctly."""
    with patch("lgtv._subnet_broadcast", return_value="192.168.1.255"), \
         patch("socket.socket") as mock_cls:
        sock = MagicMock()
        mock_cls.return_value.__enter__ = MagicMock(return_value=sock)
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)
        lgtv._send_wol("AA-BB-CC-DD-EE-FF", "192.168.1.100")
    packet = sock.sendto.call_args_list[0][0][0]
    assert packet[6:] == bytes.fromhex("AABBCCDDEEFF") * 16


def test_send_wol_sends_to_broadcast_and_direct():
    """Packet is sent to both the subnet broadcast address and the TV's IP."""
    tv_ip = "192.168.1.100"
    broadcast = "192.168.1.255"
    with patch("lgtv._subnet_broadcast", return_value=broadcast), \
         patch("socket.socket") as mock_cls:
        sock = MagicMock()
        mock_cls.return_value.__enter__ = MagicMock(return_value=sock)
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)
        lgtv._send_wol("aa:bb:cc:dd:ee:ff", tv_ip)
    destinations = [call[0][1] for call in sock.sendto.call_args_list]
    assert (broadcast, 9) in destinations
    assert (tv_ip, 9) in destinations


# ── run() — Wake-on-LAN ───────────────────────────────────────────────────────

async def test_wol_sent_on_first_failure(tmp_path, monkeypatch):
    """WoL is broadcast on first connection failure when MAC is configured."""
    monkeypatch.setattr(lgtv, "RETRY_DELAY", 0)
    ip, key = setup_files(tmp_path)
    mac_file = tmp_path / "tv_mac"
    mac_file.write_text("aa:bb:cc:dd:ee:ff\n")
    ws_drop = make_ws(ConnectionError("Server closed the WebSocket connection"))
    ws_ok   = make_ws(REGISTERED, SUCCESS)
    with patch.object(lgtv, "IP_FILE", ip), patch.object(lgtv, "KEY_FILE", key), \
         patch.object(lgtv, "MAC_FILE", mac_file), \
         patch("lgtv.ws_connect", AsyncMock(side_effect=[ws_drop, ws_ok])), \
         patch("lgtv._send_wol") as mock_wol:
        await run("on")
    mock_wol.assert_called_once_with("aa:bb:cc:dd:ee:ff", "192.168.1.100")


async def test_wol_sent_only_once(tmp_path, monkeypatch):
    """WoL is sent exactly once even when multiple retries are needed."""
    monkeypatch.setattr(lgtv, "RETRY_ATTEMPTS", 4)
    monkeypatch.setattr(lgtv, "RETRY_DELAY", 0)
    ip, key = setup_files(tmp_path)
    mac_file = tmp_path / "tv_mac"
    mac_file.write_text("aa:bb:cc:dd:ee:ff\n")
    ws_fail = MagicMock(spec=WebSocket)
    ws_fail.send = AsyncMock()
    ws_fail.recv = AsyncMock(side_effect=ConnectionError("Server closed"))
    ws_fail.close = AsyncMock()
    ws_ok = make_ws(REGISTERED, SUCCESS)
    with patch.object(lgtv, "IP_FILE", ip), patch.object(lgtv, "KEY_FILE", key), \
         patch.object(lgtv, "MAC_FILE", mac_file), \
         patch("lgtv.ws_connect", AsyncMock(side_effect=[ws_fail, ws_fail, ws_ok])), \
         patch("lgtv._send_wol") as mock_wol:
        await run("on")
    mock_wol.assert_called_once()


async def test_wol_not_sent_without_mac_file(tmp_path, monkeypatch):
    """No WoL when MAC file does not exist."""
    monkeypatch.setattr(lgtv, "RETRY_DELAY", 0)
    ip, key = setup_files(tmp_path)
    mac_file = tmp_path / "tv_mac"   # not created
    ws_drop = make_ws(ConnectionError("Server closed"))
    ws_ok   = make_ws(REGISTERED, SUCCESS)
    with patch.object(lgtv, "IP_FILE", ip), patch.object(lgtv, "KEY_FILE", key), \
         patch.object(lgtv, "MAC_FILE", mac_file), \
         patch("lgtv.ws_connect", AsyncMock(side_effect=[ws_drop, ws_ok])), \
         patch("lgtv._send_wol") as mock_wol:
        await run("on")
    mock_wol.assert_not_called()


async def test_wol_not_sent_for_off_command(tmp_path, monkeypatch):
    """WoL is never sent for the off command."""
    monkeypatch.setattr(lgtv, "RETRY_DELAY", 0)
    ip, key = setup_files(tmp_path)
    mac_file = tmp_path / "tv_mac"
    mac_file.write_text("aa:bb:cc:dd:ee:ff\n")
    ws = make_ws(REGISTERED, SUCCESS)
    with patch.object(lgtv, "IP_FILE", ip), patch.object(lgtv, "KEY_FILE", key), \
         patch.object(lgtv, "MAC_FILE", mac_file), \
         patch("lgtv.ws_connect", AsyncMock(return_value=ws)), \
         patch("lgtv._send_wol") as mock_wol:
        await run("off")
    mock_wol.assert_not_called()


# ── main() ────────────────────────────────────────────────────────────────────

def test_main_no_args(monkeypatch):
    monkeypatch.setattr("sys.argv", ["lgtv.py"])
    with pytest.raises(SystemExit):
        lgtv.main()


def test_main_bad_arg(monkeypatch):
    monkeypatch.setattr("sys.argv", ["lgtv.py", "restart"])
    with pytest.raises(SystemExit):
        lgtv.main()


def test_main_on(monkeypatch):
    monkeypatch.setattr("sys.argv", ["lgtv.py", "on"])
    with patch("lgtv.run", AsyncMock()) as mock_run:
        lgtv.main()
    mock_run.assert_called_once_with("on", None)


def test_main_on_with_input(monkeypatch):
    monkeypatch.setattr("sys.argv", ["lgtv.py", "on", "HDMI_3"])
    with patch("lgtv.run", AsyncMock()) as mock_run:
        lgtv.main()
    mock_run.assert_called_once_with("on", "HDMI_3")


def test_main_config(monkeypatch):
    monkeypatch.setattr("sys.argv", ["lgtv.py", "config", "--show"])
    with patch("lgtv.config_command") as mock_cfg:
        lgtv.main()
    mock_cfg.assert_called_once_with(["--show"])


def test_main_off(monkeypatch):
    monkeypatch.setattr("sys.argv", ["lgtv.py", "off"])
    with patch("lgtv.run", AsyncMock()) as mock_run:
        lgtv.main()
    mock_run.assert_called_once_with("off", None)


def test_main_pair(monkeypatch):
    monkeypatch.setattr("sys.argv", ["lgtv.py", "pair"])
    with patch("lgtv.run", AsyncMock()) as mock_run:
        lgtv.main()
    mock_run.assert_called_once_with("pair", None)


# ── config_command ───────────────────────────────────────────────────────────

def test_config_sets_ip_and_input(tmp_path):
    ip = tmp_path / "tv_ip"
    inp = tmp_path / "tv_input"
    with patch.object(lgtv, "IP_FILE", ip), patch.object(lgtv, "INPUT_FILE", inp):
        lgtv.config_command(["--ip", "192.168.1.50", "--input", "HDMI_3"])
    assert ip.read_text().strip() == "192.168.1.50"
    assert inp.read_text().strip() == "HDMI_3"


def test_config_preserves_unset_values(tmp_path):
    ip = tmp_path / "tv_ip"
    ip.write_text("192.168.1.30\n")
    inp = tmp_path / "tv_input"
    inp.write_text("HDMI_3\n")
    with patch.object(lgtv, "IP_FILE", ip), patch.object(lgtv, "INPUT_FILE", inp):
        lgtv.config_command(["--input", "HDMI_2"])
    assert ip.read_text().strip() == "192.168.1.30"   # untouched
    assert inp.read_text().strip() == "HDMI_2"


def test_config_clears_input(tmp_path):
    ip = tmp_path / "tv_ip"
    ip.write_text("192.168.1.30\n")
    inp = tmp_path / "tv_input"
    inp.write_text("HDMI_3\n")
    with patch.object(lgtv, "IP_FILE", ip), patch.object(lgtv, "INPUT_FILE", inp):
        lgtv.config_command(["--input", "none"])
    assert not inp.exists()


def test_config_show(tmp_path, capsys):
    ip = tmp_path / "tv_ip"
    ip.write_text("192.168.1.30\n")
    inp = tmp_path / "tv_input"
    inp.write_text("HDMI_3\n")
    with patch.object(lgtv, "IP_FILE", ip), patch.object(lgtv, "INPUT_FILE", inp):
        lgtv.config_command(["--show"])
    out = capsys.readouterr().out
    assert "192.168.1.30" in out
    assert "HDMI_3" in out


def test_config_bad_flag(tmp_path):
    with patch.object(lgtv, "IP_FILE", tmp_path / "tv_ip"), \
         patch.object(lgtv, "INPUT_FILE", tmp_path / "tv_input"):
        with pytest.raises(SystemExit, match="Unknown config option"):
            lgtv.config_command(["--bogus"])


# ── lgtv-sleep.service ────────────────────────────────────────────────────────

_SLEEP_SVC = pathlib.Path(__file__).parent.parent / "systemd" / "lgtv-sleep.service"


@pytest.fixture(scope="module")
def sleep_svc():
    return _SLEEP_SVC.read_text()


def test_sleep_service_off_on_suspend(sleep_svc):
    assert "ExecStart=/etc/lgtvcontrol/lgtv-off.sh" in sleep_svc


def test_sleep_service_on_on_resume(sleep_svc):
    assert "ExecStop=/etc/lgtvcontrol/lgtv-on.sh" in sleep_svc


def test_sleep_service_before_sleep_target(sleep_svc):
    assert "Before=sleep.target" in sleep_svc


def test_sleep_service_wantedby_sleep_target(sleep_svc):
    assert "WantedBy=sleep.target" in sleep_svc


def test_sleep_service_remain_after_exit(sleep_svc):
    assert "RemainAfterExit=yes" in sleep_svc


# ── Deactivation & state toggle ───────────────────────────────────────────────

def test_is_disabled_false_by_default(tmp_path):
    disabled_file = tmp_path / "disabled"
    with patch.object(lgtv, "DISABLED_FILE", disabled_file):
        assert not lgtv.is_disabled()


def test_is_disabled_true_when_file_exists(tmp_path):
    disabled_file = tmp_path / "disabled"
    disabled_file.touch()
    with patch.object(lgtv, "DISABLED_FILE", disabled_file):
        assert lgtv.is_disabled()


def test_disable_command_creates_file(tmp_path):
    disabled_file = tmp_path / "disabled"
    with patch.object(lgtv, "DISABLED_FILE", disabled_file), \
         patch("lgtv.send_notification") as mock_notify:
        lgtv.disable_command()
    assert disabled_file.exists()
    mock_notify.assert_called_once_with("LG TV Control", "Auto-power sync is now DEACTIVATED", "media-playback-pause")


def test_enable_command_removes_file(tmp_path):
    disabled_file = tmp_path / "disabled"
    disabled_file.touch()
    with patch.object(lgtv, "DISABLED_FILE", disabled_file), \
         patch("lgtv.send_notification") as mock_notify:
        lgtv.enable_command()
    assert not disabled_file.exists()
    mock_notify.assert_called_once_with("LG TV Control", "Auto-power sync is now ACTIVATED", "video-display")


def test_enable_command_missing_ok(tmp_path):
    disabled_file = tmp_path / "disabled"
    with patch.object(lgtv, "DISABLED_FILE", disabled_file), \
         patch("lgtv.send_notification"):
        lgtv.enable_command()
    assert not disabled_file.exists()


def test_toggle_command_disables_when_enabled(tmp_path):
    disabled_file = tmp_path / "disabled"
    with patch.object(lgtv, "DISABLED_FILE", disabled_file), \
         patch("lgtv.send_notification"):
        lgtv.toggle_command()
    assert disabled_file.exists()


def test_toggle_command_enables_when_disabled(tmp_path):
    disabled_file = tmp_path / "disabled"
    disabled_file.touch()
    with patch.object(lgtv, "DISABLED_FILE", disabled_file), \
         patch("lgtv.send_notification"):
        lgtv.toggle_command()
    assert not disabled_file.exists()


def test_status_command_when_active(tmp_path, capsys):
    ip, key = setup_files(tmp_path)
    mac = tmp_path / "tv_mac"
    mac.write_text("aa:bb:cc:dd:ee:ff\n")
    inp = tmp_path / "tv_input"
    inp.write_text("HDMI_3\n")
    disabled_file = tmp_path / "disabled"

    with patch.object(lgtv, "IP_FILE", ip), patch.object(lgtv, "KEY_FILE", key), \
         patch.object(lgtv, "MAC_FILE", mac), patch.object(lgtv, "INPUT_FILE", inp), \
         patch.object(lgtv, "DISABLED_FILE", disabled_file), \
         patch("shutil.which", return_value=None):
        lgtv.status_command()

    out = capsys.readouterr().out
    assert "ACTIVATED (auto-power sync active)" in out
    assert "192.168.1.100" in out
    assert "aa:bb:cc:dd:ee:ff" in out
    assert "HDMI_3" in out
    assert "Present" in out


def test_status_command_when_deactivated(tmp_path, capsys):
    ip, key = setup_files(tmp_path)
    disabled_file = tmp_path / "disabled"
    disabled_file.touch()

    with patch.object(lgtv, "IP_FILE", ip), patch.object(lgtv, "KEY_FILE", key), \
         patch.object(lgtv, "MAC_FILE", tmp_path / "tv_mac"), \
         patch.object(lgtv, "INPUT_FILE", tmp_path / "tv_input"), \
         patch.object(lgtv, "DISABLED_FILE", disabled_file), \
         patch("shutil.which", return_value=None):
        lgtv.status_command()

    out = capsys.readouterr().out
    assert "DEACTIVATED (auto-power sync paused)" in out


def test_send_notification(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/notify-send" if cmd == "notify-send" else None)
    with patch("subprocess.run") as mock_sub:
        lgtv.send_notification("Title", "Message", "icon-name")
    mock_sub.assert_called_once()
    args = mock_sub.call_args[0][0]
    assert "/usr/bin/notify-send" in args
    assert "Title" in args
    assert "Message" in args


# ── run() with auto and deactivation ──────────────────────────────────────────

async def test_run_auto_skips_when_deactivated(tmp_path, capsys):
    """When deactivated, auto runs immediately return without network activity."""
    disabled_file = tmp_path / "disabled"
    disabled_file.touch()
    with patch.object(lgtv, "DISABLED_FILE", disabled_file), \
         patch("lgtv.ws_connect") as mock_conn, \
         patch("lgtv._send_wol") as mock_wol:
        await run("on", auto=True)
    mock_conn.assert_not_called()
    mock_wol.assert_not_called()
    out = capsys.readouterr().out
    assert "LG TV control is deactivated — skipping auto on" in out


async def test_run_manual_runs_even_when_deactivated(tmp_path, capsys):
    """Manual run proceeds with a note even if auto-sync is deactivated."""
    ip, key = setup_files(tmp_path)
    disabled_file = tmp_path / "disabled"
    disabled_file.touch()
    ws = make_ws(REGISTERED, SUCCESS)
    with patch.object(lgtv, "IP_FILE", ip), patch.object(lgtv, "KEY_FILE", key), \
         patch.object(lgtv, "DISABLED_FILE", disabled_file), \
         patch("lgtv.ws_connect", AsyncMock(return_value=ws)):
        await run("on", auto=False)
    err = capsys.readouterr().err
    assert "Note: LG TV auto-sync is currently DEACTIVATED" in err


# ── CLI subcommands ───────────────────────────────────────────────────────────

def test_main_disable(monkeypatch):
    monkeypatch.setattr("sys.argv", ["lgtv.py", "disable"])
    with patch("lgtv.disable_command") as mock_cmd:
        lgtv.main()
    mock_cmd.assert_called_once()


def test_main_deactivate_alias(monkeypatch):
    monkeypatch.setattr("sys.argv", ["lgtv.py", "deactivate"])
    with patch("lgtv.disable_command") as mock_cmd:
        lgtv.main()
    mock_cmd.assert_called_once()


def test_main_enable(monkeypatch):
    monkeypatch.setattr("sys.argv", ["lgtv.py", "enable"])
    with patch("lgtv.enable_command") as mock_cmd:
        lgtv.main()
    mock_cmd.assert_called_once()


def test_main_activate_alias(monkeypatch):
    monkeypatch.setattr("sys.argv", ["lgtv.py", "activate"])
    with patch("lgtv.enable_command") as mock_cmd:
        lgtv.main()
    mock_cmd.assert_called_once()


def test_main_toggle(monkeypatch):
    monkeypatch.setattr("sys.argv", ["lgtv.py", "toggle"])
    with patch("lgtv.toggle_command") as mock_cmd:
        lgtv.main()
    mock_cmd.assert_called_once()


def test_main_status(monkeypatch):
    monkeypatch.setattr("sys.argv", ["lgtv.py", "status"])
    with patch("lgtv.status_command") as mock_cmd:
        lgtv.main()
    mock_cmd.assert_called_once()


def test_main_on_auto(monkeypatch):
    monkeypatch.setattr("sys.argv", ["lgtv.py", "on", "--auto"])
    with patch("lgtv.run", AsyncMock()) as mock_run:
        lgtv.main()
    mock_run.assert_called_once_with("on", None, auto=True)


def test_main_off_auto(monkeypatch):
    monkeypatch.setattr("sys.argv", ["lgtv.py", "off", "--auto"])
    with patch("lgtv.run", AsyncMock()) as mock_run:
        lgtv.main()
    mock_run.assert_called_once_with("off", None, auto=True)


def test_main_help(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["lgtv.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        lgtv.main()
    assert exc.value.code == 0
    assert "Usage: lgtv.py" in capsys.readouterr().out


# ── Wrapper templates ─────────────────────────────────────────────────────────

_ON_TPL = pathlib.Path(__file__).parent.parent / "scripts" / "lgtv-on.sh.tpl"
_OFF_TPL = pathlib.Path(__file__).parent.parent / "scripts" / "lgtv-off.sh.tpl"


def test_on_tpl_checks_disabled():
    content = _ON_TPL.read_text()
    assert "/etc/lgtvcontrol/disabled" in content
    assert "--auto" in content


def test_off_tpl_checks_disabled():
    content = _OFF_TPL.read_text()
    assert "/etc/lgtvcontrol/disabled" in content
    assert "--auto" in content


# ── uninstall.sh comprehensive coverage ───────────────────────────────────────

_UNINSTALL_SH = pathlib.Path(__file__).parent.parent / "uninstall.sh"


def test_uninstall_covers_all_services():
    content = _UNINSTALL_SH.read_text()
    assert "lgtv-startup" in content
    assert "lgtv-shutdown" in content
    assert "lgtv-sleep" in content
    assert "systemctl stop" in content
    assert "systemctl disable" in content
    assert "daemon-reload" in content


def test_uninstall_covers_legacy_paths():
    content = _UNINSTALL_SH.read_text()
    assert "/opt/lgtvcontrol" in content
    assert ".aiopylgtv.sqlite" in content
    assert "/etc/lgtvcontrol" in content
    assert "/usr/local/bin/lgtv" in content
    assert "bazzite-lgtv" in content


def test_uninstall_covers_selinux_rules():
    content = _UNINSTALL_SH.read_text()
    assert "semanage fcontext -d" in content
    assert "restorecon" in content




@pytest.mark.parametrize("raw, expected", [
    ("HDMI3", "HDMI_3"), ("hdmi 2", "HDMI_2"), ("HDMI-1", "HDMI_1"),
    ("HDMI_4", "HDMI_4"), ("COMP_1", "COMP_1"), ("com.webos.app.livetv", "com.webos.app.livetv"),
])
def test_normalize_input(raw, expected):
    assert lgtv.normalize_input(raw) == expected


async def test_on_normalizes_legacy_input(tmp_path):
    ip, key = setup_files(tmp_path)
    input_file = tmp_path / "tv_input"
    input_file.write_text("HDMI3\n")
    ws = make_ws(REGISTERED, SUCCESS, SUCCESS)
    with patch.object(lgtv, "IP_FILE", ip), patch.object(lgtv, "KEY_FILE", key), \
         patch.object(lgtv, "INPUT_FILE", input_file), \
         patch("lgtv.INPUT_SWITCH_DELAY", 0), \
         patch("lgtv.ws_connect", AsyncMock(return_value=ws)):
        await run("on")
    switch = json.loads(ws.send.call_args_list[2].args[0])
    assert switch["payload"] == {"inputId": "HDMI_3"}


# ── tray applet & desktop entries ─────────────────────────────────────────────

_REPO = pathlib.Path(__file__).parent.parent


@pytest.mark.parametrize("script", ["lgtv-tray.py", "lgtv-gui.py", "lgtv-list-inputs.py", "lgtv-diagnose.py"])
def test_helper_scripts_compile(script):
    path = _REPO / "scripts" / script
    compile(path.read_text(), str(path), "exec")


@pytest.mark.parametrize("entry", sorted((_REPO / "desktop").glob("*.desktop")), ids=lambda p: p.name)
def test_desktop_entries_valid(entry):
    lines = entry.read_text().splitlines()
    assert lines[0] == "[Desktop Entry]"
    keys = dict(line.split("=", 1) for line in lines[1:] if "=" in line)
    assert keys["Type"] == "Application"
    assert keys["Exec"].startswith("lgtv ")


def test_tray_command_execs_tray_script(monkeypatch):
    monkeypatch.setattr("sys.argv", ["lgtv.py", "tray"])
    with patch("os.execv", side_effect=SystemExit(0)) as mock_execv:   # execv never returns
        with pytest.raises(SystemExit):
            lgtv.main()
    argv = mock_execv.call_args.args[1]
    assert argv[1].endswith("lgtv-tray.py")
