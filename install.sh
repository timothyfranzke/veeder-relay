#!/bin/bash
set -e

APP_DIR="/opt/veeder-relay"
CONFIG_DIR="/etc/veeder-relay"
SYSTEMD_DIR="/etc/systemd/system"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Veeder Root Relay Installer ==="

# Check for root
if [ "$(id -u)" -ne 0 ]; then
    echo "Error: Run this script with sudo"
    exit 1
fi

# Install dependencies
echo "Installing dependencies..."
pip3 install pyserial --break-system-packages 2>/dev/null || pip3 install pyserial
apt-get install -y socat > /dev/null 2>&1 || true

# Create application directory
echo "Installing application to ${APP_DIR}..."
mkdir -p "$APP_DIR"
cp "$SCRIPT_DIR/relay.py" "$APP_DIR/relay.py"
cp "$SCRIPT_DIR/integration_test.py" "$APP_DIR/integration_test.py"
cp "$SCRIPT_DIR/veeder" "$APP_DIR/veeder"
chmod +x "$APP_DIR/relay.py" "$APP_DIR/integration_test.py" "$APP_DIR/veeder"

# Install CLI tool to PATH
ln -sf "$APP_DIR/veeder" /usr/local/bin/veeder
echo "  CLI tool installed: veeder"

# Create config directory and copy example config if none exists
echo "Setting up configuration in ${CONFIG_DIR}..."
mkdir -p "$CONFIG_DIR"
if [ ! -f "$CONFIG_DIR/config.json" ]; then
    cp "$SCRIPT_DIR/config.example.json" "$CONFIG_DIR/config.json"
    echo "  Config created at $CONFIG_DIR/config.json — edit this for your site"
else
    echo "  Config already exists, skipping (won't overwrite)"
fi

# Add current user to dialout group for serial port access
REAL_USER="${SUDO_USER:-$USER}"
if id -nG "$REAL_USER" | grep -qw dialout; then
    echo "User $REAL_USER already in dialout group"
else
    echo "Adding $REAL_USER to dialout group for serial port access..."
    usermod -aG dialout "$REAL_USER"
    echo "  NOTE: Log out and back in for group change to take effect"
fi

# Configure firewall
echo "Configuring firewall..."
apt-get install -y ufw > /dev/null 2>&1 || true

# Read server host/port from config to allow outbound
if [ -f "$CONFIG_DIR/config.json" ]; then
    SERVER_HOST=$(python3 -c "import json; print(json.load(open('$CONFIG_DIR/config.json'))['server']['host'])")
    SERVER_PORT=$(python3 -c "import json; print(json.load(open('$CONFIG_DIR/config.json'))['server']['port'])")
else
    SERVER_HOST=$(python3 -c "import json; print(json.load(open('$SCRIPT_DIR/config.example.json'))['server']['host'])")
    SERVER_PORT=$(python3 -c "import json; print(json.load(open('$SCRIPT_DIR/config.example.json'))['server']['port'])")
fi

# Reset firewall to clean state
ufw --force reset > /dev/null 2>&1

# Default: deny incoming, deny outgoing
ufw default deny incoming > /dev/null 2>&1
ufw default deny outgoing > /dev/null 2>&1

# Allow outbound to central server
echo "  Allowing outbound to server ${SERVER_HOST}:${SERVER_PORT}"
ufw allow out to "$SERVER_HOST" port "$SERVER_PORT" proto tcp > /dev/null 2>&1

# Allow DNS (needed to resolve hostnames if server is a domain)
ufw allow out 53 > /dev/null 2>&1

# Allow outbound HTTPS (needed for Pi Connect and apt updates)
ufw allow out 443/tcp > /dev/null 2>&1

# Allow SSH in (needed for Pi Connect remote access)
ufw allow in 22/tcp > /dev/null 2>&1

# Enable firewall
ufw --force enable > /dev/null 2>&1
echo "  Firewall configured and enabled"

# Install systemd units
echo "Installing systemd service and timer..."
cp "$SCRIPT_DIR/veeder-relay.service" "$SYSTEMD_DIR/"
cp "$SCRIPT_DIR/veeder-relay.timer" "$SYSTEMD_DIR/"
systemctl daemon-reload

# Enable timer to start on boot
systemctl enable veeder-relay.timer
systemctl start veeder-relay.timer

echo ""
echo "=== Installation complete ==="
echo ""
echo "Config:    $CONFIG_DIR/config.json"
echo "App:       $APP_DIR/relay.py"
echo "Schedule:  Top of every hour (and 1 min after boot)"
echo ""
echo "Useful commands:"
echo "  veeder status             # Health check and last run info"
echo "  veeder logs               # View recent logs"
echo "  veeder logs --errors      # View only errors"
echo "  veeder config             # Show current config"
echo "  sudo veeder config edit   # Edit config interactively"
echo "  sudo veeder run           # Trigger a relay run now"
echo "  sudo veeder test          # Run integration tests"
