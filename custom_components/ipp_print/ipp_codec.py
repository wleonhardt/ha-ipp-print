"""Bounded IPP value/group decoder, independent of transport and job policy."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Resolution:
    x: int
    y: int
    units: int  # 3 = dots/inch, 4 = dots/cm


@dataclass(frozen=True)
class LocalizedText:
    language: str
    text: str


@dataclass(frozen=True)
class UnknownValue:
    tag: int
    raw: bytes


@dataclass
class AttributeGroup:
    tag: int
    attributes: dict[str, list]


@dataclass
class IppResponse:
    version: bytes
    status: int
    request_id: int
    groups: list[AttributeGroup]

    def attributes(self, tags: tuple[int, ...] | None = None) -> dict[str, list]:
        result: dict[str, list] = {}
        for group in self.groups:
            if tags is None or group.tag in tags:
                for name, values in group.attributes.items():
                    result.setdefault(name, []).extend(values)
        return result


class _Reader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.offset = 8
        self.count = 0

    def take(self, size: int) -> bytes:
        if self.offset + size > len(self.data):
            raise ValueError("truncated IPP attribute")
        result = self.data[self.offset:self.offset + size]
        self.offset += size
        return result

    def field(self) -> bytes:
        return self.take(int.from_bytes(self.take(2), "big"))

    def record(self) -> tuple[int, str, bytes]:
        self.count += 1
        if self.count > 8192:
            raise ValueError("too many IPP values")
        tag = self.take(1)[0]
        if tag < 0x10:
            return tag, "", b""
        name = self.field().decode("utf-8", "replace")
        if len(name) > 255:
            raise ValueError("IPP attribute name too long")
        return tag, name, self.field()

    def value(self, tag: int, raw: bytes, depth: int = 0):
        if tag in (0x21, 0x23):
            if len(raw) != 4:
                raise ValueError("IPP integer/enum must contain four bytes")
            return int.from_bytes(raw, "big", signed=True)
        if tag == 0x22:
            if raw not in (b"\x00", b"\x01"):
                raise ValueError("invalid IPP boolean")
            return raw == b"\x01"
        if tag == 0x33:
            if len(raw) != 8:
                raise ValueError("IPP integer range must contain eight bytes")
            return (int.from_bytes(raw[:4], "big", signed=True),
                    int.from_bytes(raw[4:], "big", signed=True))
        if tag == 0x32:
            if len(raw) != 9 or raw[8] not in (3, 4):
                raise ValueError("invalid IPP resolution")
            x, y = int.from_bytes(raw[:4], "big", signed=True), int.from_bytes(raw[4:8], "big", signed=True)
            if x <= 0 or y <= 0:
                raise ValueError("invalid IPP resolution")
            return Resolution(x, y, raw[8])
        if tag in (0x35, 0x36):
            if len(raw) < 4:
                raise ValueError("truncated IPP localized text")
            length = int.from_bytes(raw[:2], "big")
            offset = 2 + length
            if offset + 2 > len(raw):
                raise ValueError("truncated IPP language")
            text_length = int.from_bytes(raw[offset:offset + 2], "big")
            if offset + 2 + text_length != len(raw):
                raise ValueError("invalid IPP localized text length")
            return LocalizedText(raw[2:offset].decode("utf-8", "replace"),
                                 raw[offset + 2:].decode("utf-8", "replace"))
        if tag == 0x34:
            if raw or depth >= 8:
                raise ValueError("invalid or too deeply nested IPP collection")
            members: dict[str, list] = {}
            current = None
            while True:
                member_tag, name, data = self.record()
                if name:
                    raise ValueError("IPP collection member must have an empty attribute name")
                if member_tag == 0x37:
                    if data or current is not None and not members[current]:
                        raise ValueError("invalid IPP collection end")
                    return members
                if member_tag == 0x4A:
                    if current is not None and not members[current]:
                        raise ValueError("IPP collection member has no value")
                    current = data.decode("utf-8", "replace")
                    if not current or len(current) > 255 or current in members:
                        raise ValueError("invalid IPP collection member name")
                    members[current] = []
                elif member_tag < 0x10 or current is None:
                    raise ValueError("invalid IPP collection")
                else:
                    members[current].append(self.value(member_tag, data, depth + 1))
        if tag in (0x37, 0x4A):
            raise ValueError("IPP collection delimiter outside a collection")
        if tag in (0x41, 0x42, 0x44, 0x45, 0x46, 0x47, 0x48, 0x49):
            return raw.decode("utf-8", "replace")
        return UnknownValue(tag, raw)


def decode_response(data: bytes) -> IppResponse:
    if len(data) < 8:
        raise ValueError("IPP response too short")
    if len(data) > 1024 * 1024:
        raise ValueError("IPP response exceeds the 1 MiB limit")
    if data[:2] not in (b"\x01\x00", b"\x01\x01", b"\x02\x00", b"\x02\x01", b"\x02\x02"):
        raise ValueError("invalid IPP response version")
    reader = _Reader(data)
    groups = []
    current = None
    group = None
    while reader.offset < len(data):
        tag, name, raw = reader.record()
        if tag == 3:
            return IppResponse(data[:2], int.from_bytes(data[2:4], "big"),
                               int.from_bytes(data[4:8], "big"), groups)
        if tag < 0x10:
            if not tag or len(groups) >= 128:
                raise ValueError("invalid or too many IPP groups")
            group = AttributeGroup(tag, {})
            groups.append(group)
            current = None
            continue
        if group is None:
            raise ValueError("IPP value outside an attribute group")
        current = name or current
        value = reader.value(tag, raw)
        if current is None:
            raise ValueError("IPP value without an attribute name")
        group.attributes.setdefault(current, []).append(value)
    raise ValueError("IPP response missing end-of-attributes")
