#!/usr/bin/env python3
"""List all available HDMI inputs from LG TV via WebSocket.

Usage:
    python3 lgtv-list-inputs.py [TV_IP] [CLIENT_KEY]

If TV_IP or CLIENT_KEY are not provided, reads from:
    /etc/lgtvcontrol/tv_ip
    /etc/lgtvcontrol/client.key

Displays all available inputs with their IDs and labels.
"""

import asyncio
import base64
import json
import os
import ssl
import struct
import sys
from pathlib import Path

CONF_DIR = Path("/etc/lgtvcontrol")
KEY_FILE = CONF_DIR / "client.key"
IP_FILE = CONF_DIR / "tv_ip"
TIMEOUT = 10

# Standard LG remote app manifest (same as lgtv.py)
MANIFEST = {
    "appVersion": "1.1",
    "manifestVersion": 1,
    "permissions": [
        "LAUNCH", "LAUNCH_WEBAPP", "APP_TO_APP", "CLOSE",
        "TEST_OPEN", "TEST_PROTECTED", "CONTROL_AUDIO", "CONTROL_DISPLAY",
        "CONTROL_INPUT_JOYSTICK", "CONTROL_INPUT_MEDIA_RECORDING",
        "CONTROL_INPUT_MEDIA_PLAYBACK", "CONTROL_INPUT_TV", "CONTROL_POWER",
        "CONTROL_TV_SCREEN", "READ_APP_STATUS", "READ_CURRENT_CHANNEL",
        "READ_INPUT_DEVICE_LIST", "READ_NETWORK_STATE", "READ_RUNNING_APPS",
        "READ_TV_CHANNEL_LIST", "WRITE_NOTIFICATION_TOAST", "READ_POWER_STATE",
        "READ_COUNTRY_INFO", "CONTROL_INPUT_TEXT", "CONTROL_MOUSE_AND_KEYBOARD",
        "READ_INSTALLED_APPS", "READ_SETTINGS", "READ_STORAGE_DEVICE_LIST",
    ],
    "signatures": [{"signature": (
        "eyJhbGdvcml0aG0iOiJSU0EtU0hBMjU2Iiwia2V5SWQiOiJ0ZXN0LXNpZ25pbm"
        "ctY2VydCIsInNpZ25hdHVyZVZlcnNpb24iOjF9.hrVRgjCwXVvE2OOSpDZ58hR"
        "+59aFNwYDyjQgKk3auukd7pcegmE2CzPCa0bJ0ZsRAcKkCTJrWo5iDzNhMBWRy"
        "aMOv5zWSrthlf7G128qvIlpMT0YNY+n/FaOHE73uLrS/g7swl3/qH/BGFG2Hu4"
        "RlL48eb3lLKqTt2xKHdCs6Cd4RMfJPYnzgvI4BNrFUKsjkcu+WD4OO2A27Pq1n"
        "50cMchmcaXadJhGrOqH5YmHdOCj5NSHzJYrsW0HPlpuAx/ECMeIZYDh6RMqaFM"
        "2DXzdKX9NmmyqzJ3o/0lkk/N97gfVRLW5hA29yeAwaCViZNCP8iC9aO0q9fQoj"
        "oa7NQnAtw=="
    ), "signatureVersion": 1}],
    "signed": {
        "appId": "com.lge.test",
        "created": "20140509",
        "localizedAppNames": {
            "": "LG Remote App",
            "ko-KR": "리모컨 앱",
            "zxx-XX": "ЛГ Rэмotэ AПП",
        },
        "localizedVendorNames": {"": "LG Electronics"},
        "permissions": [
            "TEST_SECURE", "CONTROL_INPUT_TEXT", "CONTROL_MOUSE_AND_KEYBOARD",
            "READ_INSTALLED_APPS", "READ_LGE_SDX", "READ_NOTIFICATIONS",
            "SEARCH", "WRITE_SETTINGS", "WRITE_NOTIFICATION_ALERT",
            "CONTROL_POWER", "READ_CURRENT_CHANNEL", "READ_RUNNING_APPS",
            "READ_UPDATE_INFO", "UPDATE_FROM_REMOTE_APP",
            "READ_LGE_TV_INPUT_EVENTS", "READ_TV_CURRENT_TIME",
        ],
        "serial": "2f930e2d2cfe083771f68e4fe7bb07",
        "vendorId": "com.lge",
    },
}


class WebSocket:
    """Minimal WebSocket client."""
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self._r = reader
        self._w = writer

    async def send(self, text: str) -> None:
        data = text.encode()
        n = len(data)
        mask = os.urandom(4)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        header = b'\x81'  # FIN=1, opcode=1 (text)
        if n < 126:
            header += bytes([0x80 | n]) + mask
        elif n < 65536:
            header += bytes([0xFE]) + struct.pack('>H', n) + mask
        else:
            header += bytes([0xFF]) + struct.pack('>Q', n) + mask
        self._w.write(header + masked)
        await self._w.drain()

    async def recv(self) -> str:
        header = await self._r.readexactly(2)
        opcode = header[0] & 0x0F
        length = header[1] & 0x7F
        if length == 126:
            length = struct.unpack('>H', await self._r.readexactly(2))[0]
        elif length == 127:
            length = struct.unpack('>Q', await self._r.readexactly(8))[0]
        payload = await self._r.readexactly(length)
        if opcode == 8:  # close frame
            raise ConnectionError("Server closed the WebSocket connection")
        return payload.decode()

    async def close(self) -> None:
        try:
            self._w.write(b'\x88\x80' + os.urandom(4))
            await self._w.drain()
        except Exception:
            pass
        self._w.close()
        try:
            await self._w.wait_closed()
        except Exception:
            pass


async def ws_connect(host: str, port: int, ctx: ssl.SSLContext) -> WebSocket:
    """Connect to TV and perform WebSocket upgrade."""
    reader, writer = await asyncio.open_connection(host, port, ssl=ctx)
    key = base64.b64encode(os.urandom(16)).decode()
    writer.write((
        f"GET / HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        f"Upgrade: websocket\r\n"
        f"Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        f"Sec-WebSocket-Version: 13\r\n"
        f"\r\n"
    ).encode())
    await writer.drain()
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = await reader.read(4096)
        if not chunk:
            raise ConnectionError("Connection closed during WebSocket handshake")
        buf += chunk
    if b" 101 " not in buf.split(b"\r\n")[0]:
        raise ConnectionError(
            f"WebSocket upgrade failed: {buf[:200].decode(errors='replace')}"
        )
    return WebSocket(reader, writer)


async def _request(ws: WebSocket, req_id: int, uri: str, payload: dict) -> dict:
    """Send an SSAP request and return the parsed response message."""
    await ws.send(json.dumps({
        "id": req_id,
        "type": "request",
        "uri": f"ssap://{uri}",
        "payload": payload,
    }))
    raw = await asyncio.wait_for(ws.recv(), timeout=TIMEOUT)
    return json.loads(raw)


async def list_inputs(tv_ip: str, client_key: str) -> None:
    """Connect to TV, register, and query available inputs."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    try:
        print(f"Connecting to TV at {tv_ip}...", file=sys.stderr)
        ws = await asyncio.wait_for(ws_connect(tv_ip, 3001, ctx), timeout=TIMEOUT)
        print(f"Connected. Registering...", file=sys.stderr)
    except asyncio.TimeoutError:
        sys.exit(f"Connection timed out after {TIMEOUT}s")
    except (OSError, ConnectionError) as e:
        sys.exit(f"Connection failed: {e}")

    try:
        # Register
        await ws.send(json.dumps({
            "type": "register",
            "id": "register_0",
            "payload": {
                "client-key": client_key,
                "forcePairing": False,
                "manifest": MANIFEST,
                "pairingType": "PROMPT",
            },
        }))

        # Wait for registration response
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=TIMEOUT)
            msg = json.loads(raw)
            mtype = msg.get("type")

            if mtype == "response" and msg.get("payload", {}).get("pairingType") == "PROMPT":
                sys.exit(
                    "Stored key was rejected by TV — please re-pair:\n"
                    f"  sudo python3 {Path(__file__).parent / 'lgtv.py'} pair"
                )

            if mtype == "registered":
                print(f"Registered successfully.", file=sys.stderr)
                break

            if mtype == "error":
                sys.exit(f"Registration error: {msg.get('payload', msg)}")

        # Query available inputs
        print(f"\nQuerying available inputs...\n", file=sys.stderr)
        response = await _request(ws, 1, "tv/getInputList", {})
        
        print(f"Raw response: {json.dumps(response, indent=2)}\n", file=sys.stderr)

        # Try alternative endpoints if getInputList doesn't work
        if not response.get("payload") or "devices" not in response.get("payload", {}):
            print("getInputList returned empty payload, trying alternative endpoints...\n", file=sys.stderr)
            
            # Try tv/getExternalInputList
            print("Trying tv/getExternalInputList...", file=sys.stderr)
            response = await _request(ws, 2, "tv/getExternalInputList", {})
            print(f"Response: {json.dumps(response, indent=2)}\n", file=sys.stderr)

        if response.get("type") == "error":
            print(f"Error querying inputs: {response.get('payload', response)}")
        else:
            payload = response.get("payload", {})
            devices = payload.get("devices", [])

            if not devices:
                print("No inputs found in response.")
                print("\nFull response for debugging:")
                print(json.dumps(response, indent=2))
            else:
                print("Available HDMI Inputs:")
                print("=" * 70)
                for device in devices:
                    input_id = device.get("id", "")
                    label = device.get("label", "")
                    icon_url = device.get("iconUrl", "")
                    
                    print(f"  ID:    {input_id}")
                    print(f"  Label: {label}")
                    if icon_url:
                        print(f"  Icon:  {icon_url}")
                    print()

    except asyncio.TimeoutError:
        sys.exit(f"Timed out waiting for TV response")
    except Exception as e:
        sys.exit(f"Error: {e}")
    finally:
        await ws.close()


def main():
    args = sys.argv[1:]

    # Get TV IP
    if args:
        tv_ip = args[0]
    else:
        try:
            tv_ip = IP_FILE.read_text().strip()
        except FileNotFoundError:
            sys.exit(f"TV IP not configured. Usage: {Path(__file__).name} <TV_IP> [CLIENT_KEY]")

    # Get client key
    if len(args) > 1:
        client_key = args[1]
    else:
        try:
            client_key = KEY_FILE.read_text().strip()
        except FileNotFoundError:
            sys.exit(f"No client key found at {KEY_FILE}. Usage: {Path(__file__).name} <TV_IP> <CLIENT_KEY>")

    asyncio.run(list_inputs(tv_ip, client_key))


if __name__ == "__main__":
    main()
