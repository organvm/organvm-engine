"""Tests for the testament OSC bridge."""

from __future__ import annotations

import json
import socket
import struct
from pathlib import Path
from typing import Any

import pytest

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


class _FakeSocket:
    sent_payloads: list[tuple[bytes, tuple[str, int]]] = []

    def __init__(self, family: int, socket_type: int) -> None:
        self.family = family
        self.socket_type = socket_type
        self.timeout: float | None = None
        self.closed = False

    def settimeout(self, timeout: float) -> None:
        self.timeout = timeout

    def sendto(self, payload: bytes, address: tuple[str, int]) -> int:
        self.sent_payloads.append((payload, address))
        return len(payload)

    def close(self) -> None:
        self.closed = True


def _fake_socket(
    monkeypatch: pytest.MonkeyPatch,
) -> list[tuple[bytes, tuple[str, int]]]:
    sent_payloads: list[tuple[bytes, tuple[str, int]]] = []

    class FakeSocket(_FakeSocket):
        pass

    FakeSocket.sent_payloads = sent_payloads
    monkeypatch.setattr(socket, "socket", FakeSocket)
    return sent_payloads


def _read_string(buf: bytes, offset: int) -> tuple[str, int]:
    end = buf.index(b"\x00", offset)
    value = buf[offset:end].decode("ascii")
    advanced = end + 1
    if advanced % 4:
        advanced += 4 - (advanced % 4)
    return value, advanced


def _decode_message(buf: bytes) -> tuple[str, list[Any]]:
    address, offset = _read_string(buf, 0)
    tags, offset = _read_string(buf, offset)
    assert tags.startswith(",")

    args: list[Any] = []
    for tag in tags[1:]:
        if tag == "f":
            args.append(struct.unpack(">f", buf[offset : offset + 4])[0])
            offset += 4
        elif tag == "i":
            args.append(struct.unpack(">i", buf[offset : offset + 4])[0])
            offset += 4
        elif tag == "s":
            value, offset = _read_string(buf, offset)
            args.append(value)
        else:
            raise AssertionError(f"unexpected tag {tag}")
    return address, args


def test_encode_message_is_4byte_aligned():
    packet = encode_message("/testament/master", [0.5])

    assert len(packet) % 4 == 0


def test_encode_message_round_trips_floats():
    packet = encode_message("/testament/env", [0.1, 0.5, 0.75, 2.0])

    address, args = _decode_message(packet)

    assert address == "/testament/env"
    assert len(args) == 4
    for got, want in zip(args, [0.1, 0.5, 0.75, 2.0], strict=True):
        assert abs(got - want) < 1e-6


def test_encode_message_round_trips_mixed_types():
    packet = encode_message("/testament/voice/0", [220.0, 0.7, "sine", 5.0, -1.0])

    address, args = _decode_message(packet)

    assert address == "/testament/voice/0"
    assert args[2] == "sine"
    assert abs(args[0] - 220.0) < 1e-3
    assert abs(args[4] - (-1.0)) < 1e-6


def test_encode_message_rejects_unknown_type():
    with pytest.raises(TypeError):
        encode_message("/bad", [object()])


def test_encode_bundle_has_header_and_elements():
    messages = [OscMessage("/a", [1.0]), OscMessage("/b", ["x"])]

    bundle = encode_bundle(messages)

    assert bundle.startswith(b"#bundle\x00")
    assert bundle[8:16] == struct.pack(">Q", 1)
    size = struct.unpack(">i", bundle[16:20])[0]
    assert size > 0
    address, _args = _decode_message(bundle[20 : 20 + size])
    assert address == "/a"


def test_build_osc_messages_covers_all_sections():
    testament = render_sonic_params(
        organ_densities={"META": 0.6, "I": 0.5},
        organ_repo_counts={"META": 10, "I": 8},
        met_ratio=0.5,
        total_repos=18,
    )

    messages = build_osc_messages(testament)
    addrs = [message.address for message in messages]

    assert "/testament/master" in addrs
    assert "/testament/bpm" in addrs
    assert "/testament/env" in addrs
    assert "/testament/filter" in addrs
    assert sum(1 for addr in addrs if addr.startswith("/testament/voice/")) == 8


def test_build_osc_messages_voice_args_are_typed():
    testament = render_sonic_params(total_repos=10)

    voice = next(
        message for message in build_osc_messages(testament)
        if message.address == "/testament/voice/0"
    )
    freq, _amp, waveform, _detune, pan = voice.args

    assert isinstance(freq, float)
    assert isinstance(waveform, str)
    assert isinstance(pan, float)


def test_send_dry_run_does_not_transmit():
    messages = [OscMessage("/testament/master", [0.5])]

    result = send_to_synth(messages, dry_run=True)

    assert result.dry_run is True
    assert result.sent is False
    assert result.byte_count > 0
    assert result.host == DEFAULT_HOST
    assert result.port == DEFAULT_PORT
    assert result.messages == ["/testament/master 0.5"]


def test_send_live_bundle_sends_one_datagram(monkeypatch):
    sent_payloads = _fake_socket(monkeypatch)
    messages = [
        OscMessage("/testament/master", [0.5]),
        OscMessage("/testament/bpm", [120.0]),
    ]

    result = send_to_synth(
        messages,
        host="127.0.0.1",
        port=19000,
        dry_run=False,
        as_bundle=True,
    )

    assert result.sent is True
    assert result.error is None
    assert len(sent_payloads) == 1
    payload, address = sent_payloads[0]
    assert address == ("127.0.0.1", 19000)
    assert payload.startswith(b"#bundle\x00")


def test_send_live_per_message_sends_separate_datagrams(monkeypatch):
    sent_payloads = _fake_socket(monkeypatch)
    messages = [
        OscMessage("/testament/master", [0.5]),
        OscMessage("/testament/bpm", [120.0]),
    ]

    result = send_to_synth(
        messages,
        host="127.0.0.1",
        port=19000,
        dry_run=False,
        as_bundle=False,
    )

    assert result.sent is True
    assert len(sent_payloads) == 2
    first, address = sent_payloads[0]
    decoded_address, args = _decode_message(first)
    assert address == ("127.0.0.1", 19000)
    assert decoded_address == "/testament/master"
    assert abs(args[0] - 0.5) < 1e-6


def test_build_parser_has_bridge_subcommand():
    parser = build_parser()

    args = parser.parse_args(["testament", "bridge"])

    assert args.command == "testament"
    assert args.subcommand == "bridge"
    assert args.send is False


def test_build_parser_bridge_accepts_flags():
    parser = build_parser()

    args = parser.parse_args(
        [
            "testament",
            "bridge",
            "--send",
            "--host",
            "10.0.0.1",
            "--port",
            "9000",
            "--per-message",
            "--json",
        ],
    )

    assert args.send is True
    assert args.host == "10.0.0.1"
    assert args.port == 9000
    assert args.per_message is True
    assert args.json is True


def test_bridge_dry_run_output(capsys):
    parser = build_parser()
    args = parser.parse_args(["testament", "bridge", "--registry", MOCK_REGISTRY])

    rc = cmd_testament_bridge(args)
    out = capsys.readouterr().out

    assert rc == 0
    assert "Testament Sonic Bridge" in out
    assert "[dry-run]" in out
    assert "/testament/master" in out
    assert "--send" in out


def test_bridge_json_dry_run(capsys):
    parser = build_parser()
    args = parser.parse_args(["testament", "bridge", "--json", "--registry", MOCK_REGISTRY])

    rc = cmd_testament_bridge(args)
    data = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert data["dry_run"] is True
    assert data["sent"] is False
    assert data["message_count"] > 0
    assert data["byte_count"] > 0
    assert isinstance(data["messages"], list)


def test_bridge_uses_registry_status_counts(capsys):
    parser = build_parser()
    args = parser.parse_args(["testament", "bridge", "--json", "--registry", MOCK_REGISTRY])

    rc = cmd_testament_bridge(args)
    data = json.loads(capsys.readouterr().out)
    voice_message = next(
        message for message in data["messages"]
        if message.startswith("/testament/voice/0 ")
    )
    _address, _freq, _amp, waveform, _detune, _pan = voice_message.split()

    assert rc == 0
    assert waveform == "tri"


def test_bridge_live_send_via_cli(capsys, monkeypatch):
    sent_payloads = _fake_socket(monkeypatch)
    parser = build_parser()
    args = parser.parse_args(
        [
            "testament",
            "bridge",
            "--send",
            "--host",
            "127.0.0.1",
            "--port",
            "19000",
            "--registry",
            MOCK_REGISTRY,
        ],
    )

    rc = cmd_testament_bridge(args)
    out = capsys.readouterr().out

    assert rc == 0
    assert "Transmitted" in out
    assert len(sent_payloads) == 1
    payload, address = sent_payloads[0]
    assert address == ("127.0.0.1", 19000)
    assert payload.startswith(b"#bundle\x00")
