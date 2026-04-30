#!/usr/bin/env python3
"""
proxy_control.py — Start/stop the mitmproxy traffic capture for RöX.

Usage:
    python proxy_control.py start    # enable proxy + launch mitmproxy
    python proxy_control.py stop     # disable proxy
    python proxy_control.py status   # show current proxy state
    python proxy_control.py cert     # open certificate for Keychain trust (one-time setup)
    python proxy_control.py read     # pretty-print last 20 game server captures

The script handles macOS networksetup proxy toggling automatically.
"""

import json
import os
import subprocess
import sys
import time

PROXY_HOST = "127.0.0.1"
PROXY_PORT = 8080
VENV_MITMDUMP = os.path.join(os.path.dirname(__file__), ".venv", "bin", "mitmdump")
SNIFFER_SCRIPT = os.path.join(os.path.dirname(__file__), "rox_sniffer.py")
TRAFFIC_DIR = os.path.join(os.path.dirname(__file__), "rox_traffic")
GAME_LOG = os.path.join(TRAFFIC_DIR, "game_server.jsonl")
WS_LOG   = os.path.join(TRAFFIC_DIR, "websocket.jsonl")
CERT_PATH = os.path.expanduser("~/.mitmproxy/mitmproxy-ca-cert.pem")


def _get_wifi_interface() -> str:
    """Return the active Wi-Fi network service name."""
    out = subprocess.check_output(["networksetup", "-listallnetworkservices"],
                                   text=True)
    for line in out.splitlines():
        if "Wi-Fi" in line or "WiFi" in line or "AirPort" in line:
            return line.strip().lstrip("*").strip()
    return "Wi-Fi"  # fallback


def enable_proxy() -> None:
    iface = _get_wifi_interface()
    print(f"Setting system proxy → {PROXY_HOST}:{PROXY_PORT}  (interface: {iface})")
    subprocess.run(["networksetup", "-setwebproxy",       iface, PROXY_HOST, str(PROXY_PORT)], check=True)
    subprocess.run(["networksetup", "-setsecurewebproxy", iface, PROXY_HOST, str(PROXY_PORT)], check=True)
    print("✅ Proxy enabled")


def disable_proxy() -> None:
    iface = _get_wifi_interface()
    print(f"Disabling system proxy  (interface: {iface})")
    subprocess.run(["networksetup", "-setwebproxystate",       iface, "off"], check=True)
    subprocess.run(["networksetup", "-setsecurewebproxystate", iface, "off"], check=True)
    print("✅ Proxy disabled")


def status_proxy() -> None:
    iface = _get_wifi_interface()
    print(f"\n── HTTP proxy ({iface}) ──")
    subprocess.run(["networksetup", "-getwebproxy", iface])
    print(f"\n── HTTPS proxy ({iface}) ──")
    subprocess.run(["networksetup", "-getsecurewebproxy", iface])


def open_cert() -> None:
    """Generate the cert (by running mitmdump briefly) then open in Keychain."""
    if not os.path.exists(CERT_PATH):
        print("Generating mitmproxy CA certificate (runs for 2s then stops)…")
        proc = subprocess.Popen([VENV_MITMDUMP, "--listen-port", str(PROXY_PORT)])
        time.sleep(2)
        proc.terminate()
    if os.path.exists(CERT_PATH):
        print(f"Opening {CERT_PATH} in Keychain Access…")
        print("👉 In Keychain: double-click → Trust → Always Trust → Save Changes")
        subprocess.run(["open", CERT_PATH])
    else:
        print(f"Certificate not found at {CERT_PATH}")
        print("Run 'python proxy_control.py start' first to generate it.")


def start_capture() -> None:
    """Enable proxy and launch mitmproxy in foreground."""
    os.makedirs(TRAFFIC_DIR, exist_ok=True)
    enable_proxy()
    print(f"\nStarting mitmproxy on port {PROXY_PORT}…")
    print(f"Traffic will be logged to: {TRAFFIC_DIR}/")
    print("Press Ctrl+C to stop (proxy will be automatically disabled)\n")
    try:
        subprocess.run([
            VENV_MITMDUMP,
            "--listen-port", str(PROXY_PORT),
            "--set", "block_global=false",
            "--set", "ssl_insecure=true",   # don't verify upstream certs (captures more)
            "-s", SNIFFER_SCRIPT,
        ])
    except KeyboardInterrupt:
        pass
    finally:
        print("\nStopping…")
        disable_proxy()


def read_captures(n: int = 20) -> None:
    """Pretty-print the last N game server captures."""
    for label, path in [("🎮 Game Server", GAME_LOG), ("⚡ WebSocket", WS_LOG)]:
        if not os.path.exists(path):
            print(f"{label}: no captures yet ({path})")
            continue
        with open(path) as f:
            lines = f.readlines()
        if not lines:
            print(f"{label}: empty")
            continue
        recent = lines[-n:]
        print(f"\n{'='*60}")
        print(f"{label} — last {len(recent)} of {len(lines)} total")
        print('='*60)
        for line in recent:
            try:
                r = json.loads(line)
                print(f"\n[{r.get('time','?')}] {r.get('method','?')} {r.get('host','?')}{r.get('path','?')[:60]}")
                print(f"  Status: {r.get('status','?')}  Content-Type: {r.get('content_type','?')[:50]}")
                body = r.get('resp_body', '')
                if body:
                    print(f"  Body preview: {str(body)[:200]}")
            except Exception:
                print(line[:200])


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    match cmd:
        case "start":
            start_capture()
        case "stop":
            disable_proxy()
        case "status":
            status_proxy()
        case "cert":
            open_cert()
        case "read":
            n = int(sys.argv[2]) if len(sys.argv) > 2 else 20
            read_captures(n)
        case _:
            print(__doc__)


if __name__ == "__main__":
    main()
