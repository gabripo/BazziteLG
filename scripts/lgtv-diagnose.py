#!/usr/bin/env python3
"""Quick diagnostics for LG TV connectivity.

Usage:
    python3 lgtv-diagnose.py [TV_IP]
"""

import socket
import sys
from pathlib import Path

CONF_DIR = Path("/etc/lgtvcontrol")
IP_FILE = CONF_DIR / "tv_ip"


def diagnose(tv_ip: str):
    print(f"Diagnosing connection to {tv_ip}...\n")

    # Test 1: Ping (ICMP)
    print("1. Testing ICMP (ping)...")
    result = socket.getaddrinfo(tv_ip, None)
    if result:
        print(f"   ✓ DNS/IP resolution works: {result[0]}")
    else:
        print(f"   ✗ Cannot resolve {tv_ip}")
        return

    # Test 2: TCP port 3001 (WebSocket port used by lgtv.py)
    print("\n2. Testing TCP connection to port 3001 (WebSocket)...")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((tv_ip, 3001))
        sock.close()
        if result == 0:
            print(f"   ✓ Port 3001 is OPEN and responding")
        else:
            print(f"   ✗ Port 3001 is CLOSED or not responding (error code: {result})")
            print(f"     This usually means:")
            print(f"     - TV is off or in deep standby")
            print(f"     - Firewall is blocking the connection")
            print(f"     - TV's WebOS service is not running")
    except socket.timeout:
        print(f"   ✗ Connection timed out (TV may be off or unreachable)")
    except Exception as e:
        print(f"   ✗ Connection error: {e}")

    # Test 3: Other common ports
    print("\n3. Testing other ports for alternative services...")
    ports = {
        22: "SSH",
        80: "HTTP",
        443: "HTTPS",
        9998: "LG web service (alt)",
        9999: "LG web service (alt)",
    }
    for port, service in ports.items():
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex((tv_ip, port))
            sock.close()
            if result == 0:
                print(f"   ✓ Port {port:5d} ({service:30s}) is OPEN")
        except:
            pass

    print("\n" + "=" * 60)
    print("NEXT STEPS:")
    print("=" * 60)
    print("• If port 3001 is CLOSED:")
    print("  1. Make sure the TV is powered ON (not in standby)")
    print("  2. Check if WebOS is fully loaded (wait 30 seconds after power-on)")
    print("  3. Try: lgtv.py on")
    print("     (this will retry multiple times and may wake the TV via WoL)")
    print("\n• If port 3001 is OPEN:")
    print("  1. TV is reachable - try again:")
    print("     python3 scripts/lgtv-list-inputs.py")
    print("  2. Increase timeout if TV is slow")


def main():
    args = sys.argv[1:]

    # Get TV IP
    if args:
        tv_ip = args[0]
    else:
        try:
            tv_ip = IP_FILE.read_text().strip()
        except FileNotFoundError:
            sys.exit(
                f"TV IP not configured.\n"
                f"Usage: {Path(__file__).name} <TV_IP>\n"
                f"Or configure it at: {IP_FILE}"
            )

    diagnose(tv_ip)


if __name__ == "__main__":
    main()
