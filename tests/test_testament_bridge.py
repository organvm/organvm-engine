"""Tests for the testament OSC bridge — issue #49 / LIMEN-076.

Covers binary OSC 1.0 encoding, typed message construction, dry-run vs. live
UDP transport (via a loopback socket), and CLI wiring.
"""

from __future__ import annotations

import socket
import struct
from pathlib import Path

from organvm_engine.cli import build_parser
from organvm_engine.cli.testament import cmd_testament_bridge
from organvm_engine.testament.osc_bridge import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    OscMessage,
    build_osc_messages,
    encode_bundle,
    encode_message,
    send_to_synth,
)
from organvm_engine.testament.renderers.sonic import render_sonic_params

FIXTURES = Path(__file__).parent / "fixtures"
MOCK_REGISTRY = str(FIXTURES / "registry-minimal.json")


# ---------------------------------------------------------------------------
# Minimal OSC decoder — used only to verify our encoder round-trips.
# ---------------------------------------------------------------------------

def _read_string(buf: bytes, offset: int) -> tuple[str, int]:
    end = buf.index(b"\x00", offset)
    value = buf[offset:end].decode("ascii")
    # advance past the null and align to 4 bytes
    advanced = end + 1
    if advanced % 4:
        advanced += 4 - (advanced % 4)
    return value, advanced


def _decode_message(buf: bytes) -> tuple[str, list]:
    address, offset = _read_string(buf, 0)
    tags, offset = _read_string(buf, offset)
    assert tags.startswith(",")
    args: list = []
    for tag in tags[1:]:
        if tag == "f":
            args.append(struct.unpack(">f", buf[offset:offset + 4])[0])
            offset += 4
        elif tag == "i":
            args.append(struct.unpack(">i", buf[offset:offset + 4])[0])
            offset += 4
        elif tag == "s":
            value, offset = _read_string(buf, offset)
            args.append(value)
        else:
            raise AssertionError(f"unexpected tag {tag}")
    return address, args


# ---------------------------------------------------------------------------
# Encoding
# ---------------------------------------------------------------------------

def test_encode_message_is_4byte_aligned():
    packet = encode_message("/testament/master", [0.5])
    assert len(packet) % 4 == 0


def test_encode_message_round_trips_floats():
    packet = encode_message("/testament/env", [0.1, 0.5, 0.75, 2.0])
    address, args = _decode_message(packet)
    assert address == "/testament/env"
    assert len(args) == 4
    for got, want in zip(args, [0.1, 0.5, 0.75, 2.0]):
        assert abs(got - want) < 1e-6


def test_encode_message_round_trips_mixed_types():
    packet = encode_message("/testament/voice/0", [220.0, 0.7, "sine", 5.0, -1.0])
    address, args = _decode_message(packet)
    assert address == "/testament/voice/0"
    assert args[2] == "sine"
    assert abs(args[0] - 220.0) < 1e-3
    assert abs(args[4] - (-1.0)) < 1e-6


def test_encode_message_rejects_unknown_type():
    import pytest

    with pytest.raises(TypeError):
        encode_message("/bad", [object()])


def test_encode_bundle_has_header_and_elements():
    msgs = [OscMessage("/a", [1.0]), OscMessage("/b", ["x"])]
    bundle = encode_bundle(msgs)
    assert bundle.startswith(b"#bundle\x00")
    # immediate timetag
    assert bundle[8:16] == struct.pack(">Q", 1)
    # first element length prefix
    size = struct.unpack(">i", bundle[16:20])[0]
    assert size > 0
    address, args = _decode_message(bundle[20:20 + size])
    assert address == "/a"


# ---------------------------------------------------------------------------
# Message construction from the sonic testament
# ---------------------------------------------------------------------------

def test_build_osc_messages_covers_all_sections():
    testament = render_sonic_params(
        organ_densities={"META": 0.6, "I": 0.5},
        organ_repo_counts={"META": 10, "I": 8},
        met_ratio=0.5,
        total_repos=18,
    )
    messages = build_osc_messages(testament)
    addrs = [m.address for m in messages]
    assert "/testament/master" in addrs
    assert "/testament/bpm" in addrs
    assert "/testament/env" in addrs
    assert "/testament/filter" in addrs
    # 8 voices
    assert sum(1 for a in addrs if a.startswith("/testament/voice/")) == 8


def test_build_osc_messages_voice_args_are_typed():
    testament = render_sonic_params(total_repos=10)
    voice = next(m for m in build_osc_messages(testament) if m.address == "/testament/voice/0")
    freq, amp, waveform, detune, pan = voice.args
    assert isinstance(freq, float)
    assert isinstance(waveform, str)
    assert isinstance(pan, float)


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------

def test_send_dry_run_does_not_transmit():
    msgs = [OscMessage("/testament/master", [0.5])]
    result = send_to_synth(msgs, dry_run=True)
    assert result.dry_run is True
    assert result.sent is False
    assert result.byte_count > 0
    assert result.host == DEFAULT_HOST
    assert result.port == DEFAULT_PORT
    assert result.messages == ["/testament/master 0.5"]


def test_send_live_bundle_reaches_loopback_socket():
    receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    receiver.bind(("127.0.0.1", 0))  # ephemeral port
    receiver.settimeout(2.0)
    _host, port = receiver.getsockname()
    try:
        msgs = [OscMessage("/testament/master", [0.5]), OscMessage("/testament/bpm", [120.0])]
        result = send_to_synth(msgs, host="127.0.0.1", port=port, dry_run=False, as_bundle=True)
        assert result.sent is True
        assert result.error is None
        data, _ = receiver.recvfrom(65535)
        assert data.startswith(b"#bundle\x00")
    finally:
        receiver.close()


def test_send_live_per_message_sends_separate_datagrams():
    receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    receiver.bind(("127.0.0.1", 0))
    receiver.settimeout(2.0)
    _host, port = receiver.getsockname()
    try:
        msgs = [OscMessage("/testament/master", [0.5]), OscMessage("/testament/bpm", [120.0])]
        result = send_to_synth(msgs, host="127.0.0.1", port=port, dry_run=False, as_bundle=False)
        assert result.sent is True
        first, _ = receiver.recvfrom(65535)
        addr, args = _decode_message(first)
        assert addr == "/testament/master"
        assert abs(args[0] - 0.5) < 1e-6
    finally:
        receiver.close()


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------

def test_build_parser_has_bridge_subcommand():
    parser = build_parser()
    args = parser.parse_args(["testament", "bridge"])
    assert args.command == "testament"
    assert args.subcommand == "bridge"
    assert args.send is False  # dry-run by default


def test_build_parser_bridge_accepts_flags():
    parser = build_parser()
    args = parser.parse_args([
        "testament", "bridge", "--send", "--host", "10.0.0.1",
        "--port", "9000", "--per-message", "--json",
    ])
    assert args.send is True
    assert args.host == "10.0.0.1"
    assert args.port == 9000
    assert args.per_message is True
    assert args.json is True


def test_bridge_dry_run_output(capsys):
    parser = build_parser()
    args = parser.parse_args(["testament", "bridge", "--registry", MOCK_REGISTRY])
    rc = cmd_testament_bridge(args)
    assert rc == 0
    out = capsys.readouterr().out
    assert "Testament Sonic Bridge" in out
    assert "[dry-run]" in out
    assert "/testament/master" in out
    assert "--send" in out


def test_bridge_json_dry_run(capsys):
    parser = build_parser()
    args = parser.parse_args(["testament", "bridge", "--json", "--registry", MOCK_REGISTRY])
    rc = cmd_testament_bridge(args)
    assert rc == 0
    import json
    data = json.loads(capsys.readouterr().out)
    assert data["dry_run"] is True
    assert data["sent"] is False
    assert data["message_count"] > 0
    assert data["byte_count"] > 0
    assert isinstance(data["messages"], list)


def test_bridge_live_send_via_cli(capsys):
    receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    receiver.bind(("127.0.0.1", 0))
    receiver.settimeout(2.0)
    _host, port = receiver.getsockname()
    try:
        parser = build_parser()
        args = parser.parse_args([
            "testament", "bridge", "--send", "--host", "127.0.0.1",
            "--port", str(port), "--registry", MOCK_REGISTRY,
        ])
        rc = cmd_testament_bridge(args)
        assert rc == 0
        out = capsys.readouterr().out
        assert "Transmitted" in out
        data, _ = receiver.recvfrom(65535)
        assert data.startswith(b"#bundle\x00")
    finally:
        receiver.close()
