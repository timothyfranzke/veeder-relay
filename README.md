# Veeder Root Relay

A lightweight relay that connects a central server to a Veeder Root tank monitoring system via a Raspberry Pi. Runs as a scheduled task — connects, relays a single command/response exchange, then exits.

## How It Works

1. The relay runs at the top of every hour (and 1 minute after boot)
2. Connects to the central server via TCP and sends the device MAC address to identify itself
3. Connects to the Veeder Root via serial (`/dev/ttyUSB0`) or TCP
4. Pipes data bidirectionally between the server and Veeder Root
5. After 30 seconds of no data, closes both connections and exits

The central server drives the exchange — it sends commands to the Veeder Root through the relay, and the relay forwards the responses back.

## Installation

### Prerequisites

- Raspberry Pi with Raspberry Pi OS
- USB-to-serial adapter connected to the Veeder Root (for serial sites)
- Network access to the central server

### Install

```bash
cd veeder-relay
sudo ./install.sh
```

This single command:

- Installs Python serial port library (`pyserial`) and `socat` (for integration tests)
- Copies the relay script, integration tests, and CLI tool to `/opt/veeder-relay/`
- Installs the `veeder` CLI command to `/usr/local/bin/`
- Creates the config file at `/etc/veeder-relay/config.json`
- Grants serial port access (adds user to `dialout` group)
- Configures the firewall (see [Security](#security))
- Sets up the systemd timer to run at the top of every hour
- Enables auto-start on boot

### Re-installing / Updating

Run the install script again. It will update the application, CLI tool, and systemd files but **will not overwrite your existing config**.

## Configuration

The config file lives at `/etc/veeder-relay/config.json`. You can view it with `veeder config` or edit it interactively with `sudo veeder config edit`.

### Serial site (default)

```json
{
  "server": {
    "host": "192.168.1.90",
    "port": 10002
  },
  "veeder_root": {
    "connection": "serial",
    "serial_port": "/dev/ttyUSB0",
    "baud_rate": 9600,
    "parity": "odd",
    "data_bits": 7,
    "stop_bits": 1
  },
  "idle_timeout_seconds": 30
}
```

### TCP site

```json
{
  "server": {
    "host": "192.168.1.90",
    "port": 10002
  },
  "veeder_root": {
    "connection": "tcp",
    "host": "192.168.1.91",
    "port": 10003
  },
  "idle_timeout_seconds": 30
}
```

## CLI Tool

The `veeder` command is installed to `/usr/local/bin/` and provides everything you need to manage the relay from the command line.

### Quick reference

| Command | Description |
|---|---|
| `veeder status` | Health check — timer, last run result, config, serial port, firewall, recent errors |
| `veeder logs` | View the last 20 log entries with errors highlighted |
| `veeder logs --errors` | Show only errors and warnings |
| `veeder logs -n 50` | Show the last 50 log entries |
| `veeder config` | Display the current configuration |
| `sudo veeder config edit` | Interactive config editor — walks through each field |
| `sudo veeder run` | Trigger a relay run immediately and follow the logs |
| `sudo veeder test` | Run integration tests |

### Checking device health

```bash
$ veeder status
=== Veeder Relay Status ===

  Timer:       enabled and active
  Next run:    Wed 2026-04-22 17:00:00 UTC
  Last run:    Wed 2026-04-22 16:00:01 UTC
  Last result: success

  Server:      192.168.1.90:10002
  Veeder Root: Serial /dev/ttyUSB0 @ 9600 baud
  Timeout:     30s
  Serial port: OK (/dev/ttyUSB0)
  Firewall:    active

  No recent errors
```

### Viewing logs

```bash
$ veeder logs
  (last 20 entries, errors in red, warnings in yellow)

$ veeder logs --errors
  (only errors and warnings)

$ veeder logs -n 100
  (last 100 entries)
```

### Editing configuration

```bash
$ sudo veeder config edit
=== Edit Configuration ===
  Press Enter to keep current value, or type a new value.

  Server
    Host [192.168.1.90]:
    Port [10002]:

  Veeder Root
    Connection type [serial] (serial/tcp):
    Serial port [/dev/ttyUSB0]:
    Baud rate [9600]:
    Parity [odd] (odd/even/none):
    Data bits [7]:
    Stop bits [1]:

  Idle timeout (seconds) [30]:

  Save to /etc/veeder-relay/config.json? [y/N] y
  Config saved.
```

### Running the relay manually

```bash
$ sudo veeder run
  Starting relay...
  Relay started. Viewing logs:
  (live log output follows)
```

### Changing the schedule

Edit `/etc/systemd/system/veeder-relay.timer` and change the `OnCalendar` line:

```ini
OnCalendar=*:00          # Top of every hour (default)
OnCalendar=*:0/30        # Every 30 minutes
OnCalendar=*:0/15        # Every 15 minutes
OnCalendar=daily         # Once a day at midnight
```

Then reload:

```bash
sudo systemctl daemon-reload
```

### Stopping the relay

```bash
sudo systemctl stop veeder-relay.timer
sudo systemctl disable veeder-relay.timer
```

## Security

### Firewall

The install script configures `ufw` with a restrictive firewall:

| Rule | Direction | Purpose |
|---|---|---|
| Deny all incoming | In | Pi does not accept any unsolicited connections |
| Deny all outgoing | Out | Locked down by default |
| Allow server IP:port | Out | The central server TCP connection |
| Allow port 53 | Out | DNS resolution |
| Allow port 443 | Out | Pi Connect and OS security updates |
| Allow port 22 | In | SSH access via Pi Connect |

The allowed server IP and port are read from the config file during installation. If the server address changes, re-run `sudo ./install.sh` to update the firewall rules.

### No Listening Ports

The relay only makes **outbound** connections. It does not run a web server, API, or any other service that listens for incoming connections. This eliminates the most common attack vector for IoT devices.

### Remote Access

Remote access is provided by [Raspberry Pi Connect](https://www.raspberrypi.com/software/connect/), which requires authentication and uses encrypted tunnels. No ports are exposed to the local network or internet for remote management.

### Serial Port Access

Serial port permissions are managed via the `dialout` group. Only users in this group can access `/dev/ttyUSB0`.

## Troubleshooting

### "Permission denied" on serial port

The user needs to be in the `dialout` group. The install script does this automatically, but you need to log out and back in for it to take effect:

```bash
groups    # Check if 'dialout' is listed
```

If not, add it manually and reboot:

```bash
sudo usermod -aG dialout $USER
sudo reboot
```

### Relay runs but can't connect to server

Check status and config:

```bash
veeder status
veeder config
```

### Relay runs but no data from Veeder Root

Verify the serial cable is connected and the correct port is configured:

```bash
veeder status    # Check serial port status
ls /dev/ttyUSB*  # Check which USB serial devices are present
```

Check the serial settings (baud rate, parity, data bits) match the Veeder Root's configuration:

```bash
veeder config
```

### Checking for errors

```bash
veeder logs --errors
```

### Running a full diagnostic

```bash
sudo veeder test
```

This runs health checks (config, permissions, firewall, connectivity) and full end-to-end relay tests with mock servers.

## File Locations

| File | Purpose |
|---|---|
| `/opt/veeder-relay/relay.py` | The relay application |
| `/opt/veeder-relay/integration_test.py` | Integration test suite |
| `/opt/veeder-relay/veeder` | CLI tool source |
| `/usr/local/bin/veeder` | CLI tool (symlink) |
| `/etc/veeder-relay/config.json` | Site configuration |
| `/etc/systemd/system/veeder-relay.service` | systemd service unit |
| `/etc/systemd/system/veeder-relay.timer` | systemd timer (schedule) |

## Running Tests

### Unit tests (development machine)

```bash
pip3 install pytest pyserial
python3 -m pytest test_relay.py -v
```

### Integration tests (on the Pi, after install)

```bash
sudo veeder test
```

This runs two suites:

**Health checks** — quick validation that the install is correct:
- Config file exists and is valid
- Relay script is installed
- pyserial is installed
- Serial port exists and is accessible (serial sites only)
- systemd timer and service are installed and enabled
- Firewall is active
- Central server is reachable

**Relay tests** — full end-to-end data flow:
- Spins up a mock central server and mock Veeder Root
- Runs the relay against them
- Verifies the MAC address is sent to the server
- Verifies data is relayed in both directions
- Tests both TCP-to-TCP and TCP-to-serial (using virtual serial ports via `socat`)
