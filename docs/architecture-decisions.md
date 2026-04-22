# Architecture Decisions

## Why We Rebuilt in Python

The original relay was built in Node.js with ~6,700 lines of application code, including an AWS IoT sidecar, OTA update manager, dashboard server, retry handler, and status manager. The actual job — relay a single command/response between a central server and a Veeder Root — required none of this.

The complexity was the root cause of the field issues we encountered:

- **Serial port locking:** The Node.js app used an EventEmitter-based lifecycle with an `isRunning` flag that controlled whether the serial port got closed during shutdown. When the flag was out of sync (which happened in several edge cases), the port was never released. The next run would fail with "Cannot lock port" and trigger a crash/reboot loop.
- **Overlapping connections:** PM2 would start a new instance on schedule even if the previous run was still active. Both instances tried to open the serial port simultaneously, causing lock conflicts.
- **Unhandled errors:** No error listener was registered on the serial client's EventEmitter. When a connection error occurred, Node.js threw an unhandled rejection that crashed the process without cleanup.
- **Production/development switching:** The AWS IoT sidecar required certificate management, IoT thing name configuration, and shadow state — too many moving parts for a field install.

The Python rebuild is 113 lines. It runs as a one-shot script: connect, relay, exit. There are no EventEmitters, no lifecycle state machines, no shutdown orchestration. The serial port is always released when the process exits because there is nothing to prevent it.

### Why Python specifically

- **Pre-installed on every Raspberry Pi** — no runtime to install.
- **`pyserial` is pure Python** — no native compilation required. The Node.js `serialport` package requires native ARM builds, which have caused installation issues on Pis.
- **`socket` and `select` are in the standard library** — no dependencies for TCP communication.
- **Simple to read and modify** — anyone on the team can open the single file and understand the entire system.

## Why We Removed PM2

PM2 is a Node.js process manager designed for long-running services. Our relay is not a long-running service — it runs once an hour, does its job in under a minute, and exits. Using PM2 for this introduced problems:

- **No overlap protection.** PM2's cron scheduler starts a new instance on schedule regardless of whether the previous one is still running. If a data pull took longer than the interval, two instances would fight over the serial port.
- **Unnecessary memory usage.** PM2 itself runs as a persistent daemon, consuming ~30MB of RAM on a device where memory is limited.
- **Extra dependency.** PM2 requires Node.js, which requires npm, which requires native module compilation for the serial port library. Each layer adds a potential point of failure during installation.

### What replaced it

A **systemd timer** — built into every Raspberry Pi OS installation. Two small configuration files:

- `veeder-relay.timer` — defines the schedule (top of every hour)
- `veeder-relay.service` — defines what to run (`python3 /opt/veeder-relay/relay.py`)

systemd provides everything PM2 did and more:

| Capability | PM2 | systemd |
|---|---|---|
| Scheduled execution | Yes | Yes |
| Overlap prevention | No | Yes (built-in for `Type=oneshot`) |
| Auto-start on boot | Yes | Yes |
| Log management | Writes to files (no rotation) | journald (auto-rotating, size-capped) |
| Status checking | `pm2 status` | `systemctl status veeder-relay` |
| Memory overhead | ~30MB daemon | None (part of the OS) |
| Additional dependencies | Node.js, npm | None |

## Security Measures

### Firewall

The install script configures `ufw` with a deny-all policy and explicit exceptions:

| Rule | Direction | Purpose |
|---|---|---|
| Deny all | Incoming | Pi accepts no unsolicited connections |
| Deny all | Outgoing | Nothing leaves the Pi unless explicitly allowed |
| Allow to server IP:port | Outgoing | The central server TCP connection |
| Allow port 53 | Outgoing | DNS resolution |
| Allow port 443 | Outgoing | Pi Connect and OS security updates |
| Allow port 22 | Incoming | SSH via Pi Connect |

The server IP and port are read directly from the site configuration during installation. If the server address changes, re-running the install script updates the firewall rules automatically.

This means even if the Pi were compromised via the local gas station network, it could only communicate with the central server — it cannot be used to scan, attack, or pivot to other systems.

### No Listening Ports

The relay makes **outbound connections only**. It does not run a web server, dashboard, API, or any service that accepts incoming connections. This eliminates the most common attack vector for IoT devices — exposed network services.

### No Cloud Service Dependencies

The previous architecture required AWS IoT Core certificates, MQTT connections, and device shadow state. Each of these was a potential attack surface and a point of failure. The new architecture has no cloud dependencies — the relay connects directly to the central server over TCP.

### Remote Access

Remote management is handled by [Raspberry Pi Connect](https://www.raspberrypi.com/software/connect/), which provides:

- Authenticated access (no anonymous connections)
- Encrypted tunnels (traffic is not readable on the local network)
- No exposed ports on the device's local network interface

### Serial Port Access Control

Access to the Veeder Root serial port (`/dev/ttyUSB0`) is restricted to users in the `dialout` group. The install script manages group membership automatically.

### Future Consideration: TLS

The TCP connection to the central server is currently unencrypted. If this traffic traverses the public internet (rather than a VPN or private network), adding TLS encryption is recommended. This would require:

- A ~3 line change to the relay script (Python's `ssl` module)
- The central server to accept TLS connections (e.g., via a TLS termination proxy)
