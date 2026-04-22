"""Unit tests for Veeder Root relay."""

import json
import os
import socket
import sys
import tempfile
from unittest.mock import MagicMock, patch, call

import pytest

# Allow importing relay from the same directory
sys.path.insert(0, os.path.dirname(__file__))
import relay


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

class TestLoadConfig:
    def test_loads_valid_config(self, tmp_path):
        config = {"server": {"host": "1.2.3.4", "port": 5000}, "idle_timeout_seconds": 30}
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config))

        with patch.object(relay, "CONFIG_PATH", str(config_file)):
            result = relay.load_config()

        assert result == config

    def test_raises_on_missing_file(self):
        with patch.object(relay, "CONFIG_PATH", "/nonexistent/config.json"):
            with pytest.raises(FileNotFoundError):
                relay.load_config()

    def test_raises_on_invalid_json(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text("not valid json {{{")

        with patch.object(relay, "CONFIG_PATH", str(config_file)):
            with pytest.raises(json.JSONDecodeError):
                relay.load_config()


# ---------------------------------------------------------------------------
# Connection setup
# ---------------------------------------------------------------------------

class TestConnectServer:
    @patch("relay.socket.create_connection")
    @patch("relay.get_mac_address", return_value="aabbccddeeff")
    def test_sends_mac_address_with_newline(self, mock_mac, mock_connect):
        mock_sock = MagicMock()
        mock_connect.return_value = mock_sock

        config = {"server": {"host": "1.2.3.4", "port": 5000}}
        result = relay.connect_server(config)

        mock_sock.sendall.assert_called_once_with(b"aabbccddeeff\n")
        mock_sock.setblocking.assert_called_once_with(False)
        assert result is mock_sock


class TestConnectVeederRoot:
    @patch("relay.socket.create_connection")
    def test_tcp_connection(self, mock_connect):
        mock_sock = MagicMock()
        mock_connect.return_value = mock_sock

        config = {"veeder_root": {"connection": "tcp", "host": "1.2.3.4", "port": 10003}}
        result = relay.connect_veeder_root(config)

        mock_connect.assert_called_once_with(("1.2.3.4", 10003), timeout=10)
        mock_sock.setblocking.assert_called_once_with(False)
        assert result is mock_sock

    @patch("serial.Serial")
    def test_serial_connection_with_config(self, mock_serial_class):
        mock_port = MagicMock()
        mock_serial_class.return_value = mock_port

        config = {
            "veeder_root": {
                "connection": "serial",
                "serial_port": "/dev/ttyUSB0",
                "baud_rate": 9600,
                "parity": "odd",
                "data_bits": 7,
                "stop_bits": 1,
            }
        }
        result = relay.connect_veeder_root(config)

        mock_serial_class.assert_called_once_with(
            port="/dev/ttyUSB0",
            baudrate=9600,
            parity="O",
            bytesize=7,
            stopbits=1,
            timeout=0,
        )
        assert result is mock_port

    @patch("serial.Serial")
    def test_serial_defaults_to_odd_parity(self, mock_serial_class):
        mock_serial_class.return_value = MagicMock()

        config = {
            "veeder_root": {
                "connection": "serial",
                "serial_port": "/dev/ttyUSB0",
                "baud_rate": 9600,
            }
        }
        relay.connect_veeder_root(config)

        _, kwargs = mock_serial_class.call_args
        assert kwargs["parity"] == "O"
        assert kwargs["bytesize"] == 7
        assert kwargs["stopbits"] == 1


# ---------------------------------------------------------------------------
# Relay loop
# ---------------------------------------------------------------------------

class TestRelay:
    def _make_socket_pair(self):
        """Create two mock sockets with distinct file descriptors."""
        server = MagicMock(spec=socket.socket)
        server.fileno.return_value = 10

        veeder = MagicMock(spec=socket.socket)
        veeder.fileno.return_value = 11

        return server, veeder

    @patch("relay.select.select")
    def test_forwards_server_data_to_veeder_tcp(self, mock_select):
        server, veeder = self._make_socket_pair()
        server.recv.return_value = b"\x01\x02\x03"

        # First call: server has data. Second call: idle timeout.
        mock_select.side_effect = [
            ([10], [], []),
            ([], [], []),
        ]

        relay.relay(server, veeder, idle_timeout=5)

        veeder.sendall.assert_called_once_with(b"\x01\x02\x03")

    @patch("relay.select.select")
    def test_forwards_veeder_data_to_server(self, mock_select):
        server, veeder = self._make_socket_pair()
        veeder.recv.return_value = b"\x04\x05\x06"

        mock_select.side_effect = [
            ([11], [], []),
            ([], [], []),
        ]

        relay.relay(server, veeder, idle_timeout=5)

        server.sendall.assert_called_once_with(b"\x04\x05\x06")

    @patch("relay.select.select")
    def test_exits_when_server_closes(self, mock_select):
        server, veeder = self._make_socket_pair()
        server.recv.return_value = b""  # Connection closed

        mock_select.side_effect = [([10], [], [])]

        relay.relay(server, veeder, idle_timeout=5)
        # Should return without error

    @patch("relay.select.select")
    def test_exits_when_veeder_closes(self, mock_select):
        server, veeder = self._make_socket_pair()
        veeder.recv.return_value = b""  # Connection closed

        mock_select.side_effect = [([11], [], [])]

        relay.relay(server, veeder, idle_timeout=5)
        # Should return without error

    @patch("relay.select.select")
    def test_exits_on_idle_timeout(self, mock_select):
        server, veeder = self._make_socket_pair()

        # select returns empty — timeout
        mock_select.return_value = ([], [], [])

        relay.relay(server, veeder, idle_timeout=5)

        mock_select.assert_called_once_with([10, 11], [], [10, 11], 5)

    @patch("relay.select.select")
    def test_exits_on_select_error(self, mock_select):
        server, veeder = self._make_socket_pair()

        mock_select.return_value = ([], [], [10])

        relay.relay(server, veeder, idle_timeout=5)
        # Should return without raising


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

class TestCloseConnection:
    def test_closes_connection(self):
        conn = MagicMock()
        relay.close_connection(conn)
        conn.close.assert_called_once()

    def test_does_not_raise_on_already_closed(self):
        conn = MagicMock()
        conn.close.side_effect = OSError("already closed")
        relay.close_connection(conn)  # Should not raise


class TestMain:
    @patch("relay.close_connection")
    @patch("relay.relay")
    @patch("relay.connect_veeder_root")
    @patch("relay.connect_server")
    @patch("relay.load_config")
    def test_closes_both_connections_on_relay_error(
        self, mock_config, mock_server, mock_veeder, mock_relay, mock_close
    ):
        mock_config.return_value = {"idle_timeout_seconds": 30}
        mock_srv = MagicMock()
        mock_vr = MagicMock()
        mock_server.return_value = mock_srv
        mock_veeder.return_value = mock_vr
        mock_relay.side_effect = RuntimeError("relay broke")

        with pytest.raises(SystemExit) as exc_info:
            relay.main()

        assert exc_info.value.code == 1
        assert call(mock_vr) in mock_close.call_args_list
        assert call(mock_srv) in mock_close.call_args_list

    @patch("relay.close_connection")
    @patch("relay.relay")
    @patch("relay.connect_veeder_root")
    @patch("relay.connect_server")
    @patch("relay.load_config")
    def test_exits_1_on_connection_failure(
        self, mock_config, mock_server, mock_veeder, mock_relay, mock_close
    ):
        mock_config.return_value = {"idle_timeout_seconds": 30}
        mock_server.side_effect = ConnectionRefusedError("refused")

        with pytest.raises(SystemExit) as exc_info:
            relay.main()

        assert exc_info.value.code == 1
