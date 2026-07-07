"""OSC bridge: transmit the sonic testament to the alchemical-synthesizer.

The :mod:`organvm_engine.testament.renderers.sonic` renderer turns system
metrics into synthesizer parameters and ``render_osc_messages`` emits them as
human-readable command strings. Those strings are not wire-format OSC and
cannot be sent to SuperCollider as-is.

This module closes that gap. It encodes the sonic self-portrait into binary
OSC 1.0 packets and ships them over UDP to the alchemical-synthesizer's
``TestamentReceiver.sc``. Sending is opt-in: ``dry_run`` defaults to ``True``,
matching the package convention for outward-facing side effects.
"""

from __future__ import annotations

import socket
import struct
from dataclasses import dataclass, field

from organvm_engine.testament.renderers.sonic import SonicTestament

# SuperCollider's default language port. The synthesizer receiver listens here.
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 57120

# OSC timetag meaning "play now".
_OSC_IMMEDIATE = struct.pack(">Q", 1)


@dataclass
class OscMessage:
    """A single typed OSC message bound for the synthesizer."""

    address: str
    args: list[float | int | str] = field(default_factory=list)

    def as_text(self) -> str:
        """Return a human-readable rendering of this OSC message."""
        parts = [self.address, *[_fmt_arg(arg) for arg in self.args]]
        return " ".join(parts)


@dataclass
class BridgeResult:
    """Outcome of a bridge transmission or dry-run rehearsal."""

    host: str
    port: int
    message_count: int
    byte_count: int
    sent: bool
    dry_run: bool
    as_bundle: bool
    messages: list[str] = field(default_factory=list)
    error: str | None = None


def _pad(data: bytes) -> bytes:
    """Pad data with trailing nulls to a multiple of 4 bytes."""
    remainder = len(data) % 4
    if remainder:
        return data + (b"\x00" * (4 - remainder))
    return data


def _encode_string(value: str) -> bytes:
    """Encode an OSC string: null-terminated, then null-padded to 4 bytes."""
    return _pad(value.encode("ascii", errors="replace") + b"\x00")


def encode_message(address: str, args: list[float | int | str]) -> bytes:
    """Encode an address and typed args into a binary OSC message."""
    type_tags = ","
    body = b""

    for arg in args:
        if isinstance(arg, bool):
            type_tags += "i"
            body += struct.pack(">i", int(arg))
        elif isinstance(arg, float):
            type_tags += "f"
            body += struct.pack(">f", arg)
        elif isinstance(arg, int):
            type_tags += "i"
            body += struct.pack(">i", arg)
        elif isinstance(arg, str):
            type_tags += "s"
            body += _encode_string(arg)
        else:
            raise TypeError(f"unsupported OSC argument type: {type(arg).__name__}")

    return _encode_string(address) + _encode_string(type_tags) + body


def encode_bundle(messages: list[OscMessage]) -> bytes:
    """Encode messages into a single OSC bundle with an immediate timetag."""
    packet = _encode_string("#bundle") + _OSC_IMMEDIATE
    for msg in messages:
        element = encode_message(msg.address, msg.args)
        packet += struct.pack(">i", len(element)) + element
    return packet


def build_osc_messages(testament: SonicTestament) -> list[OscMessage]:
    """Build typed OSC messages from a SonicTestament."""
    messages: list[OscMessage] = [
        OscMessage("/testament/master", [float(testament.master_amplitude)]),
    ]

    if testament.rhythm:
        messages.append(OscMessage("/testament/bpm", [float(testament.rhythm.bpm)]))

    if testament.envelope:
        envelope = testament.envelope
        messages.append(
            OscMessage(
                "/testament/env",
                [
                    float(envelope.attack),
                    float(envelope.decay),
                    float(envelope.sustain),
                    float(envelope.release),
                ],
            ),
        )

    if testament.filter:
        filter_params = testament.filter
        messages.append(
            OscMessage(
                "/testament/filter",
                [float(filter_params.cutoff), float(filter_params.resonance)],
            ),
        )

    for index, voice in enumerate(testament.voices):
        messages.append(
            OscMessage(
                f"/testament/voice/{index}",
                [
                    float(voice.frequency),
                    float(voice.amplitude),
                    voice.waveform,
                    float(voice.detune),
                    float(voice.pan),
                ],
            ),
        )

    return messages


def send_to_synth(
    messages: list[OscMessage],
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    *,
    dry_run: bool = True,
    as_bundle: bool = True,
    timeout: float = 2.0,
) -> BridgeResult:
    """Send OSC messages to the alchemical-synthesizer over UDP."""
    texts = [message.as_text() for message in messages]

    if as_bundle:
        payloads = [encode_bundle(messages)] if messages else []
    else:
        payloads = [encode_message(message.address, message.args) for message in messages]

    byte_count = sum(len(payload) for payload in payloads)

    if dry_run:
        return BridgeResult(
            host=host,
            port=port,
            message_count=len(messages),
            byte_count=byte_count,
            sent=False,
            dry_run=True,
            as_bundle=as_bundle,
            messages=texts,
        )

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        for payload in payloads:
            sock.sendto(payload, (host, port))
    except OSError as exc:
        return BridgeResult(
            host=host,
            port=port,
            message_count=len(messages),
            byte_count=byte_count,
            sent=False,
            dry_run=False,
            as_bundle=as_bundle,
            messages=texts,
            error=str(exc),
        )
    finally:
        sock.close()

    return BridgeResult(
        host=host,
        port=port,
        message_count=len(messages),
        byte_count=byte_count,
        sent=True,
        dry_run=False,
        as_bundle=as_bundle,
        messages=texts,
    )


def _fmt_arg(arg: float | int | str) -> str:
    """Render an arg for the textual form."""
    if isinstance(arg, bool):
        return str(int(arg))
    if isinstance(arg, float):
        return repr(arg)
    return str(arg)
