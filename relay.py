#!/usr/bin/env python3
"""Veeder Root relay — connects a central server to a Veeder Root via serial or TCP."""

import json
import os
import select
import socket
import sys
import uuid

CONFIG_PATH = "/etc/veeder-relay/config.json"


def get_mac_address():
    """Get the device MAC address as a hex string (no separators)."""
    mac = uuid.getnode()
    return f"{mac:012x}"


def load_config():
    """Load configuration from JSON file."""
    with open(CONFIG_PATH) as f:
        return json.load(f)


def connect_server(cfg):
    """Connect to the central server and send device ID."""
    srv = cfg["server"]
    print(f"Connecting to server {srv['host']}:{srv['port']}")
    sock = socket.create_connection((srv["host"], srv["port"]), timeout=10)
    sock.setblocking(False)

    mac = get_mac_address()
    print(f"Sending device ID: {mac}")
    sock.sendall((mac + "\n").encode())
    return sock


def connect_veeder_root(cfg):
    """Connect to the Veeder Root via serial or TCP."""
    vr = cfg["veeder_root"]

    if vr["connection"] == "tcp":
        print(f"Connecting to Veeder Root via TCP {vr['host']}:{vr['port']}")
        sock = socket.create_connection((vr["host"], vr["port"]), timeout=10)
        sock.setblocking(False)
        return sock

    # Serial connection
    import serial

    print(f"Connecting to Veeder Root via serial {vr['serial_port']} at {vr['baud_rate']} baud")
    parity_map = {"none": "N", "odd": "O", "even": "E"}
    ser = serial.Serial(
        port=vr["serial_port"],
        baudrate=vr["baud_rate"],
        parity=parity_map.get(vr.get("parity", "odd"), "O"),
        bytesize=vr.get("data_bits", 7),
        stopbits=vr.get("stop_bits", 1),
        timeout=0,
    )
    print("Serial port opened")
    return ser


def get_fileno(conn):
    """Get the file descriptor for select(), works for both sockets and serial."""
    return conn.fileno()


def relay(server, veeder, idle_timeout):
    """Pipe data between server and Veeder Root until idle timeout."""
    import serial as serial_mod

    is_serial = isinstance(veeder, serial_mod.Serial)
    fds = [server.fileno(), veeder.fileno()]

    print(f"Relaying data (idle timeout: {idle_timeout}s)")
    while True:
        readable, _, errors = select.select(fds, [], fds, idle_timeout)

        if errors:
            print("Connection error detected", file=sys.stderr)
            return

        if not readable:
            print("Idle timeout reached, closing connections")
            return

        for fd in readable:
            if fd == server.fileno():
                data = server.recv(4096)
                if not data:
                    print("Server closed connection")
                    return
                print(f"Server -> Veeder Root: {len(data)} bytes")
                if is_serial:
                    veeder.write(data)
                else:
                    veeder.sendall(data)

            elif fd == veeder.fileno():
                if is_serial:
                    data = veeder.read(4096)
                else:
                    data = veeder.recv(4096)
                if not data:
                    print("Veeder Root closed connection")
                    return
                print(f"Veeder Root -> Server: {len(data)} bytes")
                server.sendall(data)


def close_connection(conn):
    """Close a connection (socket or serial)."""
    try:
        conn.close()
    except Exception:
        pass


def main():
    config = load_config()
    idle_timeout = config.get("idle_timeout_seconds", 30)

    server = None
    veeder = None

    try:
        server = connect_server(config)
        veeder = connect_veeder_root(config)
        relay(server, veeder, idle_timeout)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        if veeder:
            close_connection(veeder)
        if server:
            close_connection(server)

    print("Done")


if __name__ == "__main__":
    main()
