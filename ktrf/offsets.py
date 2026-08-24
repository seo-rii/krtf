"""Offset contract (spec §13).

Internal span identity uses half-open intervals. The API exposes byte
(UTF-8), codepoint (Unicode scalar) and UTF-16 code-unit coordinates for
every span (REQ-OFF-001..003). Malformed UTF-8 at the API boundary is
rejected, never repaired (REQ-OFF-004; enforced in errors/resolver).
"""

from __future__ import annotations

from dataclasses import dataclass


class OffsetMap:
    """Precomputed codepoint -> byte / UTF-16 offset tables for one text."""

    def __init__(self, text: str):
        self.text = text
        n = len(text)
        byte_off = [0] * (n + 1)
        u16_off = [0] * (n + 1)
        b = 0
        u = 0
        for i, ch in enumerate(text):
            byte_off[i] = b
            u16_off[i] = u
            cp = ord(ch)
            if cp < 0x80:
                b += 1
            elif cp < 0x800:
                b += 2
            elif cp < 0x10000:
                b += 3
            else:
                b += 4
            u += 1 if cp < 0x10000 else 2
        byte_off[n] = b
        u16_off[n] = u
        self._byte = byte_off
        self._u16 = u16_off
        # reverse map byte -> codepoint (only defined on boundaries)
        self._byte_to_cp = {v: i for i, v in enumerate(byte_off)}

    def cp_to_byte(self, cp: int) -> int:
        return self._byte[cp]

    def cp_to_utf16(self, cp: int) -> int:
        return self._u16[cp]

    def byte_to_cp(self, byte: int) -> int:
        try:
            return self._byte_to_cp[byte]
        except KeyError:
            raise ValueError(f"byte offset {byte} is not a codepoint boundary")

    def span_dict(self, cp_start: int, cp_end: int) -> dict:
        """API span representation with all three coordinates (§13.2)."""
        return {
            "byte": {"start": self._byte[cp_start], "end": self._byte[cp_end]},
            "codepoint": {"start": cp_start, "end": cp_end},
            "utf16": {"start": self._u16[cp_start], "end": self._u16[cp_end]},
        }


@dataclass(frozen=True)
class Span:
    """Internal span in codepoint coordinates (converted at the API edge)."""

    start: int
    end: int

    def __len__(self) -> int:
        return self.end - self.start


def check_span_invariant(text: str, cp_start: int, cp_end: int, surface: str) -> None:
    """REQ-OFF-002: text[codepoint_start:codepoint_end] == surface."""
    actual = text[cp_start:cp_end]
    if actual != surface:
        raise AssertionError(
            f"offset invariant violated: text[{cp_start}:{cp_end}]={actual!r} != {surface!r}"
        )


def check_roundtrip(text: str, cp_start: int, cp_end: int) -> None:
    """REQ-OFF-003: byte and UTF-16 offsets round-trip to the same substring."""
    m = OffsetMap(text)
    b0, b1 = m.cp_to_byte(cp_start), m.cp_to_byte(cp_end)
    assert text.encode("utf-8")[b0:b1].decode("utf-8") == text[cp_start:cp_end]
    u0, u1 = m.cp_to_utf16(cp_start), m.cp_to_utf16(cp_end)
    enc = text.encode("utf-16-le")
    assert enc[2 * u0 : 2 * u1].decode("utf-16-le") == text[cp_start:cp_end]
