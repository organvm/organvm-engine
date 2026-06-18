"""OSC bridge — transmit the sonic testament to the alchemical-synthesizer.

The :mod:`~organvm_engine.testament.renderers.sonic` renderer turns system
metrics into synthesizer parameters and ``render_osc_messages`` emits them as
human-readable command *strings*. Those strings are not wire-format OSC — they
cannot be sent to SuperCollider as-is.

This module closes that gap. It encodes the sonic self-portrait into binary
`OSC 1.0 <https://opensoundcontrol.stanford.edu/spec-1_0.html>`_ packets and
ships them over UDP to the alchemical-synthesizer's ``TestamentReceiver.sc``
(SuperCollider's default langPort is 57120). The system plays itself — over
the network.

Pure stdlib: ``struct`` for binary packing, ``socket`` for transport. No
external OSC dependency. Sending is opt-in (``dry_run`` defaults to ``True``),
matching the package convention for outward-facing side effects.
"""

from __future__ import annotations

import socket
import struct
from dataclasses import dataclass, field

from organvm_engine.testament.renderers.sonic import SonicTestament

# SuperCollider's default language port (sclang). The alchemical-synthesizer's
# TestamentReceiver.sc binds an OSCdef listener here.
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 57120

# OSC type tags we emit. Floats for continuous parameters, strings for the
# waveform selector (sine/saw/square/tri).
_OSC_IMMEDIATE = struct.pack(">Q", 1)  # timetag meaning "play now"


@dataclass
class OscMessage:
    """A single typed OSC message bound for the synthesizer.

    Unlike the textual form produced by ``render_osc_messages``, the arguments
    here retain their Python types (``float``/``int``/``str``) so they encode to
    the correct OSC type tags.
    """

    address: str
    args: list[float | int | str] = field(default_factory=list)

    def as_text(self) -> str:
        """Human-readable rendering, matching ``render_osc_messages`` output."""
        parts = [self.address, *[_fmt_arg(a) for a in self.args]]
        return " ".join(parts)


@dataclass
class BridgeResult:
    """Outcome of a bridge transmission (or dry-run rehearsal)."""

    host: str
    port: int
    message_count: int
    byte_count: int
    sent: bool
    dry_run: bool
    as_bundle: bool
    messages: list[str] = field(default_factory=list)
    error: str | None = None


# ---------------------------------------------------------------------------
# OSC binary encoding (OSC 1.0)
# ---------------------------------------------------------------------------

def _pad(data: bytes) -> bytes:
    """Pad ``data`` with trailing nulls to a multiple of 4 bytes."""
    remainder = len(data) % 4
    if remainder:
        return data + b"\x00" * (4 - remainder)
    return data


def _encode_string(value: str) -> bytes:
    """Encode an OSC-string: null-terminated, then null-padded to 4 bytes."""
    return _pad(value.encode("ascii", errors="replace") + b"\x00")


def encode_message(address: str, args: list[float | int | str]) -> bytes:
    """Encode an address + typed args into a binary OSC message.

    Floats become ``f`` (big-endian 32-bit), ints become ``i``, strings become
    ``s``. Bools are coerced to int. Unknown types raise ``TypeError``.
    """
    type_tags = ","
    body = b""
    for arg in args:
        # bool is a subclass of int — check it first so it does not become "i"
        # silently if a caller ever passes one; we coerce to 0/1 explicitly.
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
    """Encode messages into a single OSC bundle with an immediate timetag.

    A bundle lets the synthesizer apply every parameter atomically, so the
    self-portrait does not glissando through intermediate states as individual
    messages arrive.
    """
    packet = _encode_string("#bundle") + _OSC_IMMEDIATE
    for msg in messages:
        element = encode_message(msg.address, msg.args)
        packet += struct.pack(">i", len(element)) + element
    return packet


# ---------------------------------------------------------------------------
# Build typed messages from the sonic testament
# ---------------------------------------------------------------------------

def build_osc_messages(testament: SonicTestament) -> list[OscMessage]:
    """Build typed OSC messages from a :class:`SonicTestament`.

    Mirrors the address scheme of ``render_osc_messages`` but preserves arg
    types for wire encoding.
    """
    messages: list[OscMessage] = [
        OscMessage("/testament/master", [float(testament.master_amplitude)]),
    ]

    if testament.rhythm:
        messages.append(OscMessage("/testament/bpm", [float(testament.rhythm.bpm)]))

    if testament.envelope:
        e = testament.envelope
        messages.append(OscMessage(
            "/testament/env",
            [float(e.attack), float(e.decay), float(e.sustain), float(e.release)],
        ))

    if testament.filter:
        f = testament.filter
        messages.append(OscMessage(
            "/testament/filter", [float(f.cutoff), float(f.resonance)],
        ))

    for i, v in enumerate(testament.voices):
        messages.append(OscMessage(
            f"/testament/voice/{i}",
            [float(v.frequency), float(v.amplitude), v.waveform,
             float(v.detune), float(v.pan)],
        ))

    return messages


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------

def send_to_synth(
    messages: list[OscMessage],
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    *,
    dry_run: bool = True,
    as_bundle: bool = True,
    timeout: float = 2.0,
) -> BridgeResult:
    """Send OSC messages to the alchemical-synthesizer over UDP.

    When ``dry_run`` is ``True`` (the default), nothing leaves the process: the
    packets are still encoded so the byte count is accurate, but no socket is
    opened. Set ``dry_run=False`` to actually transmit.

    When ``as_bundle`` is ``True``, all messages are wrapped in a single OSC
    bundle and sent in one datagram (atomic application). Otherwise each message
    is sent as its own datagram.
    """
    texts = [m.as_text() for m in messages]

    # Encode up front so byte_count is meaningful even in a dry run, and so an
    # encoding error surfaces before we touch the network.
    if as_bundle:
        payloads = [encode_bundle(messages)] if messages else []
    else:
        payloads = [encode_message(m.address, m.args) for m in messages]
    byte_count = sum(len(p) for p in payloads)

    if dry_run:
        return BridgeResult(
            host=host, port=port, message_count=len(messages),
            byte_count=byte_count, sent=False, dry_run=True,
            as_bundle=as_bundle, messages=texts,
        )

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        for payload in payloads:
            sock.sendto(payload, (host, port))
    except OSError as exc:
        return BridgeResult(
            host=host, port=port, message_count=len(messages),
            byte_count=byte_count, sent=False, dry_run=False,
            as_bundle=as_bundle, messages=texts, error=str(exc),
        )
    finally:
        sock.close()

    return BridgeResult(
        host=host, port=port, message_count=len(messages),
        byte_count=byte_count, sent=True, dry_run=False,
        as_bundle=as_bundle, messages=texts,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fmt_arg(arg: float | int | str) -> str:
    """Render an arg for the textual form, dropping trailing ``.0`` noise."""
    if isinstance(arg, bool):
        return str(int(arg))
    if isinstance(arg, float):
        # Match render_osc_messages' bare float repr (e.g. "220.0", "0.7").
        return repr(arg)
    return str(arg)
