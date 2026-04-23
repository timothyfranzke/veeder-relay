#!/usr/bin/env python3
"""
Integration tests for Veeder Root relay.

Run after installation to verify the system is working:
    sudo python3 /opt/veeder-relay/integration_test.py

Two test suites:
  1. Health checks  — quick validation that the install is correct
  2. Relay tests    — full end-to-end data flow with mock server and virtual serial ports
"""

import json
import os
import select
import socket
import subprocess
import sys
import threading
import time

CONFIG_PATH = "/etc/veeder-relay/config.json"
RELAY_SCRIPT = "/opt/veeder-relay/relay.py"

passed = 0
failed = 0


def result(name, ok, detail=""):
    global passed, failed
    status = "PASS" if ok else "FAIL"
    if ok:
        passed += 1
    else:
        failed += 1
    msg = f"  [{status}] {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)


# ---------------------------------------------------------------------------
# Health checks
# ---------------------------------------------------------------------------

def check_config_exists():
    ok = os.path.isfile(CONFIG_PATH)
    result("Config file exists", ok, CONFIG_PATH if ok else f"Not found at {CONFIG_PATH}")


def check_config_valid():
    try:
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
        has_server = "server" in cfg and "host" in cfg["server"] and "port" in cfg["server"]
        has_veeder = "veeder_root" in cfg and "connection" in cfg["veeder_root"]
        ok = has_server and has_veeder
        result("Config is valid JSON with required fields", ok)
    except Exception as e:
        result("Config is valid JSON with required fields", False, str(e))


def check_relay_script_exists():
    ok = os.path.isfile(RELAY_SCRIPT)
    result("Relay script installed", ok, RELAY_SCRIPT if ok else f"Not found at {RELAY_SCRIPT}")


def check_pyserial_installed():
    try:
        import serial
        result("pyserial installed", True, f"version {serial.__version__}")
    except ImportError:
        result("pyserial installed", False, "pip3 install pyserial")


def check_serial_port_exists():
    try:
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
        if cfg["veeder_root"]["connection"] != "serial":
            result("Serial port exists", True, "Skipped (TCP mode)")
            return
        port = cfg["veeder_root"]["serial_port"]
        ok = os.path.exists(port)
        result("Serial port exists", ok, port if ok else f"{port} not found — is the USB adapter plugged in?")
    except Exception as e:
        result("Serial port exists", False, str(e))


def check_serial_port_accessible():
    try:
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
        if cfg["veeder_root"]["connection"] != "serial":
            result("Serial port accessible", True, "Skipped (TCP mode)")
            return
        port = cfg["veeder_root"]["serial_port"]
        if not os.path.exists(port):
            result("Serial port accessible", False, "Port does not exist")
            return
        ok = os.access(port, os.R_OK | os.W_OK)
        result("Serial port accessible", ok,
               "Read/write OK" if ok else "Permission denied — is user in dialout group?")
    except Exception as e:
        result("Serial port accessible", False, str(e))


def check_systemd_timer():
    try:
        out = subprocess.run(
            ["systemctl", "is-enabled", "veeder-relay.timer"],
            capture_output=True, text=True
        )
        ok = out.stdout.strip() == "enabled"
        result("systemd timer enabled", ok, out.stdout.strip())
    except Exception as e:
        result("systemd timer enabled", False, str(e))


def check_systemd_service():
    try:
        out = subprocess.run(
            ["systemctl", "cat", "veeder-relay.service"],
            capture_output=True, text=True
        )
        ok = out.returncode == 0
        result("systemd service installed", ok)
    except Exception as e:
        result("systemd service installed", False, str(e))


def check_firewall():
    try:
        out = subprocess.run(["ufw", "status"], capture_output=True, text=True)
        if "inactive" in out.stdout:
            result("Firewall active", False, "ufw is inactive")
            return
        ok = "Status: active" in out.stdout
        result("Firewall active", ok)
    except FileNotFoundError:
        result("Firewall active", False, "ufw not installed")
    except Exception as e:
        result("Firewall active", False, str(e))


def check_server_reachable():
    try:
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
        host = cfg["server"]["host"]
        port = cfg["server"]["port"]
        sock = socket.create_connection((host, port), timeout=5)
        sock.close()
        result("Central server reachable", True, f"{host}:{port}")
    except socket.timeout:
        result("Central server reachable", False, f"Timeout connecting to {host}:{port}")
    except ConnectionRefusedError:
        result("Central server reachable", False, f"Connection refused at {host}:{port}")
    except Exception as e:
        result("Central server reachable", False, str(e))


# ---------------------------------------------------------------------------
# Relay integration tests (mock server + virtual serial ports)
# ---------------------------------------------------------------------------

def has_socat():
    """Check if socat is available for virtual serial port tests."""
    try:
        subprocess.run(["socat", "-V"], capture_output=True)
        return True
    except FileNotFoundError:
        return False


class MockServer:
    """A simple TCP server that sends a command and captures the response."""

    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]
        self.sock.listen(1)
        self.received_mac = None
        self.received_response = None
        self.command = None
        self.thread = None

    def start(self, command):
        """Start the server in a background thread. Sends command after receiving MAC."""
        self.command = command
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        self.sock.settimeout(15)
        try:
            conn, _ = self.sock.accept()
            conn.settimeout(10)

            # Read MAC address line
            data = b""
            while b"\n" not in data:
                chunk = conn.recv(1024)
                if not chunk:
                    return
                data += chunk
            self.received_mac = data.decode().strip()

            # Send command to relay
            time.sleep(0.2)
            conn.sendall(self.command)

            # Read response (wait long enough for serial round-trip)
            time.sleep(3)
            try:
                self.received_response = conn.recv(4096)
            except socket.timeout:
                self.received_response = b""

            conn.close()
        except Exception:
            pass
        finally:
            self.sock.close()

    def wait(self, timeout=15):
        if self.thread:
            self.thread.join(timeout)


def test_relay_tcp_to_tcp():
    """Test full relay: mock server <-> relay <-> mock Veeder Root (TCP)."""
    # Start mock Veeder Root (echoes back whatever it receives)
    vr_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    vr_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    vr_sock.bind(("127.0.0.1", 0))
    vr_port = vr_sock.getsockname()[1]
    vr_sock.listen(1)

    def veeder_root_echo():
        vr_sock.settimeout(10)
        try:
            conn, _ = vr_sock.accept()
            conn.settimeout(5)
            while True:
                data = conn.recv(4096)
                if not data:
                    break
                conn.sendall(data)
            conn.close()
        except Exception:
            pass
        finally:
            vr_sock.close()

    vr_thread = threading.Thread(target=veeder_root_echo, daemon=True)
    vr_thread.start()

    # Start mock server
    command = b"\x01i20100\x03"
    server = MockServer()
    server.start(command)

    # Write temporary config
    test_config = {
        "server": {"host": "127.0.0.1", "port": server.port},
        "veeder_root": {"connection": "tcp", "host": "127.0.0.1", "port": vr_port},
        "idle_timeout_seconds": 3,
    }

    config_path = "/tmp/veeder-relay-test-config.json"
    with open(config_path, "w") as f:
        json.dump(test_config, f)

    # Run relay with test config
    env = os.environ.copy()
    proc = subprocess.run(
        ["python3", "-c", f"""
import relay
relay.CONFIG_PATH = "{config_path}"
relay.main()
"""],
        capture_output=True, text=True, timeout=20,
        cwd=os.path.dirname(RELAY_SCRIPT),
    )

    server.wait()
    vr_thread.join(timeout=5)

    # Check results
    result("TCP relay: process exited cleanly", proc.returncode == 0,
           proc.stderr.strip() if proc.returncode != 0 else "")

    result("TCP relay: server received MAC address",
           server.received_mac is not None and len(server.received_mac) == 12,
           f"MAC: {server.received_mac}" if server.received_mac else "No MAC received")

    result("TCP relay: data relayed through to server",
           server.received_response == command,
           f"Got {server.received_response!r}" if server.received_response != command else "Echo matched")

    # Cleanup
    try:
        os.unlink(config_path)
    except Exception:
        pass


def test_relay_tcp_to_serial():
    """Test full relay: mock server <-> relay <-> virtual serial port."""
    if not has_socat():
        result("Serial relay: socat available", False,
               "Install socat for serial integration tests: sudo apt install socat")
        return

    # Create virtual serial port pair
    socat_proc = subprocess.Popen(
        ["socat", "-d", "PTY,raw,echo=0,link=/tmp/vr-test-relay", "PTY,raw,echo=0,link=/tmp/vr-test-device"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    time.sleep(1)

    if socat_proc.poll() is not None:
        result("Serial relay: virtual serial ports created", False, "socat failed to start")
        return

    result("Serial relay: virtual serial ports created", True, "/tmp/vr-test-relay <-> /tmp/vr-test-device")

    # Start echo on the device side
    def serial_echo():
        try:
            import serial
            ser = serial.Serial("/tmp/vr-test-device", 9600, timeout=0.1)
            deadline = time.time() + 15
            while time.time() < deadline:
                data = ser.read(4096)
                if data:
                    ser.write(data)
                    ser.flush()
            ser.close()
        except Exception:
            pass

    echo_thread = threading.Thread(target=serial_echo, daemon=True)
    echo_thread.start()

    # Start mock server
    command = b"\x01i20100\x03"
    server = MockServer()
    server.start(command)

    # Write temporary config
    test_config = {
        "server": {"host": "127.0.0.1", "port": server.port},
        "veeder_root": {
            "connection": "serial",
            "serial_port": "/tmp/vr-test-relay",
            "baud_rate": 9600,
            "parity": "none",
            "data_bits": 8,
            "stop_bits": 1,
        },
        "idle_timeout_seconds": 3,
    }

    config_path = "/tmp/veeder-relay-test-config.json"
    with open(config_path, "w") as f:
        json.dump(test_config, f)

    # Run relay with test config
    proc = subprocess.run(
        ["python3", "-c", f"""
import relay
relay.CONFIG_PATH = "{config_path}"
relay.main()
"""],
        capture_output=True, text=True, timeout=20,
        cwd=os.path.dirname(RELAY_SCRIPT),
    )

    server.wait()

    # Check results
    result("Serial relay: process exited cleanly", proc.returncode == 0,
           proc.stderr.strip() if proc.returncode != 0 else "")

    result("Serial relay: server received MAC address",
           server.received_mac is not None and len(server.received_mac) == 12,
           f"MAC: {server.received_mac}" if server.received_mac else "No MAC received")

    result("Serial relay: data relayed through to server",
           server.received_response == command,
           f"Got {server.received_response!r}" if server.received_response != command else "Echo matched")

    # Cleanup
    socat_proc.terminate()
    socat_proc.wait(timeout=5)
    try:
        os.unlink(config_path)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    global passed, failed

    print("=== Veeder Relay Health Checks ===\n")
    check_config_exists()
    check_config_valid()
    check_relay_script_exists()
    check_pyserial_installed()
    check_serial_port_exists()
    check_serial_port_accessible()
    check_systemd_timer()
    check_systemd_service()
    check_firewall()
    check_server_reachable()

    print("\n=== Relay Integration Tests ===\n")
    test_relay_tcp_to_tcp()
    test_relay_tcp_to_serial()

    print(f"\n=== Results: {passed} passed, {failed} failed ===")
    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
