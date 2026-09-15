"""Tests for image metadata extraction and duration parsing."""

from __future__ import annotations

import io
from typing import Any

from PIL import Image

from galleryvault.app.routers.galleries import (
    _fast_parse_gif_duration,
    _fast_parse_webp_duration,
    _inspect_image_meta,
    _skip_subblocks,
)


def _build_gif(
    frames: list[dict[str, Any]],
    *,
    has_gct: bool = True,
    has_trailer: bool = True,
) -> bytes:
    buf = bytearray()
    buf.extend(b"GIF89a")
    packed = 0x80 if has_gct else 0x00
    buf.extend((1).to_bytes(2, "little"))
    buf.extend((1).to_bytes(2, "little"))
    buf.append(packed)
    buf.extend(b"\x00\x00")
    if has_gct:
        buf.extend(b"\x00\x00\x00\xff\xff\xff")

    for f in frames:
        if f.get("has_gce", True):
            delay_cs = f.get("delay_cs", 10)
            buf.extend(b"\x21\xf9\x04\x00")
            buf.extend(int(delay_cs).to_bytes(2, "little"))
            buf.extend(b"\x00\x00")

        has_lct = f.get("has_lct", False)
        img_packed = 0x80 if has_lct else 0x00
        buf.append(0x2C)
        buf.extend(b"\x00\x00\x00\x00")
        buf.extend((1).to_bytes(2, "little"))
        buf.extend((1).to_bytes(2, "little"))
        buf.append(img_packed)
        if has_lct:
            buf.extend(b"\x00\x00\x00\xff\xff\xff")

        buf.append(0x02)
        buf.extend(b"\x01\x00\x00")

    if has_trailer:
        buf.append(0x3B)
    return bytes(buf)


def _build_webp_anmf(frames: list[int]) -> bytes:
    chunks = bytearray()
    for dur in frames:
        payload = bytearray(16)
        dur_bytes = dur.to_bytes(3, "little")
        payload[12:15] = dur_bytes
        chunks.extend(b"ANMF")
        chunks.extend((16).to_bytes(4, "little"))
        chunks.extend(payload)

    riff_size = 4 + len(chunks)
    buf = bytearray()
    buf.extend(b"RIFF")
    buf.extend(riff_size.to_bytes(4, "little"))
    buf.extend(b"WEBP")
    buf.extend(chunks)
    return bytes(buf)


def test_fast_parse_gif_duration_two_frames() -> None:
    data = _build_gif([{"delay_cs": 10}, {"delay_cs": 5}])
    stream = io.BytesIO(data)
    stream.seek(0)
    duration = _fast_parse_gif_duration(stream)
    assert duration == 150
    assert stream.tell() == 0


def test_fast_parse_gif_duration_stream_pointer_restored() -> None:
    data = _build_gif([{"delay_cs": 10}, {"delay_cs": 20}])
    stream = io.BytesIO(b"prefix" + data)
    stream.seek(6)
    duration = _fast_parse_gif_duration(stream)
    assert duration == 300
    assert stream.tell() == 6


def test_fast_parse_gif_duration_centisecond_rules() -> None:
    # delay <= 1 fallback to 100ms
    data = _build_gif([{"delay_cs": 0}, {"delay_cs": 1}, {"delay_cs": 3}])
    stream = io.BytesIO(data)
    duration = _fast_parse_gif_duration(stream)
    assert duration == 100 + 100 + 30


def test_fast_parse_gif_duration_missing_gce() -> None:
    # Frame 1 has GCE delay 5 (50ms), Frame 2 has no GCE (defaults to 100ms)
    data = _build_gif([{"has_gce": True, "delay_cs": 5}, {"has_gce": False}])
    stream = io.BytesIO(data)
    duration = _fast_parse_gif_duration(stream)
    assert duration == 150


def test_fast_parse_gif_duration_single_frame_is_none() -> None:
    data = _build_gif([{"delay_cs": 20}])
    stream = io.BytesIO(data)
    duration = _fast_parse_gif_duration(stream)
    assert duration is None
    assert stream.tell() == 0


def test_fast_parse_gif_duration_capped_120s() -> None:
    # 2 frames with 70,000ms each = 140,000ms total -> capped at 120,000ms
    data = _build_gif([{"delay_cs": 7000}, {"delay_cs": 7000}])
    stream = io.BytesIO(data)
    duration = _fast_parse_gif_duration(stream)
    assert duration == 120000


def test_fast_parse_gif_duration_corrupted_and_truncated() -> None:
    cases = [
        b"NOT_A_GIF",
        b"GIF89",
        b"GIF89a\x01\x00",
        b"GIF89a\x01\x00\x01\x00\x80\x00\x00",  # GCT flag but no GCT
        _build_gif([{"delay_cs": 10}], has_trailer=False)[:15],  # Truncated in frame
        b"GIF89a\x01\x00\x01\x00\x00\x00\x00\x99\x99\x99",  # Garbage block intro
    ]
    for case in cases:
        stream = io.BytesIO(b"abc" + case)
        stream.seek(3)
        res = _fast_parse_gif_duration(stream)
        assert res is None
        assert stream.tell() == 3


def test_fast_parse_gif_block_limit() -> None:
    # 构造 10,000 个扩展块后紧跟 2 帧正常动图帧
    valid_gif = _build_gif([{"delay_cs": 10}, {"delay_cs": 10}])
    header_lsd = valid_gif[:19]
    frames_and_trailer = valid_gif[19:]

    buf = bytearray(header_lsd)
    for _ in range(10000):
        buf.extend(b"\x21\xfe\x01A\x00")  # Comment extension subblock
    buf.extend(frames_and_trailer)

    stream = io.BytesIO(buf)
    res = _fast_parse_gif_duration(stream)
    assert res is None
    assert stream.tell() == 0

    # 对照：少量扩展块不触发上限截断，正常返回 200ms
    buf_ok = bytearray(header_lsd)
    for _ in range(10):
        buf_ok.extend(b"\x21\xfe\x01A\x00")
    buf_ok.extend(frames_and_trailer)
    stream_ok = io.BytesIO(buf_ok)
    assert _fast_parse_gif_duration(stream_ok) == 200


def test_skip_subblocks_seek_support() -> None:
    class TrackingStream(io.BytesIO):
        def __init__(self, initial_bytes: bytes) -> None:
            super().__init__(initial_bytes)
            self.seek_calls = 0

        def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
            self.seek_calls += 1
            return super().seek(offset, whence)

    # 1. 验证通过 seek 零拷贝跳过数据
    data = b"\x05HELLO\x03BYE\x00"
    stream = TrackingStream(data)
    assert _skip_subblocks(stream) is True
    assert stream.seek_calls >= 2
    assert stream.tell() == len(data)

    # 2. 验证 subblocks 超过 100,000 上限时主动返回 False
    infinite_subblocks = b"\x01A" * 100050 + b"\x00"
    assert _skip_subblocks(io.BytesIO(infinite_subblocks)) is False

    # 3. 验证 0x00 填充字节被平滑跳过且后续帧正常解析
    valid_gif = _build_gif([{"delay_cs": 10}, {"delay_cs": 10}])
    padded_gif = bytearray(valid_gif[:19])
    padded_gif.extend(b"\x00\x00\x00")
    padded_gif.extend(valid_gif[19:])
    stream_padded = io.BytesIO(padded_gif)
    assert _fast_parse_gif_duration(stream_padded) == 200


def test_fast_parse_webp_duration() -> None:
    webp_bytes = _build_webp_anmf([100, 250])
    stream = io.BytesIO(webp_bytes)
    duration = _fast_parse_webp_duration(stream)
    assert duration == 350
    assert stream.tell() == 0


def test_fast_parse_webp_duration_capped_120s() -> None:
    webp_bytes = _build_webp_anmf([80000, 80000])
    stream = io.BytesIO(webp_bytes)
    duration = _fast_parse_webp_duration(stream)
    assert duration == 120000


def test_fast_parse_webp_invalid_and_pointer_restore() -> None:
    stream = io.BytesIO(b"RIFF\x10\x00\x00\x00WEBPANMF_TRUNCATED")
    stream.seek(2)
    res = _fast_parse_webp_duration(stream)
    assert res is None
    assert stream.tell() == 2


def test_inspect_image_meta_webp() -> None:
    webp_bytes = _build_webp_anmf([150, 150])
    stream = io.BytesIO(webp_bytes)
    res = _inspect_image_meta(stream)
    assert res == {"animated": True, "duration_ms": 300}


def test_inspect_image_meta_gif() -> None:
    gif_bytes = _build_gif([{"delay_cs": 5}, {"delay_cs": 15}])
    stream = io.BytesIO(gif_bytes)
    res = _inspect_image_meta(stream)
    assert res == {"animated": True, "duration_ms": 200}


def test_inspect_image_meta_static_gif() -> None:
    # Single frame GIF is not animated
    gif_bytes = _build_gif([{"delay_cs": 10}])
    stream = io.BytesIO(gif_bytes)
    res = _inspect_image_meta(stream)
    # Pillow opens single frame GIF -> is_animated False
    assert res["animated"] is False
    assert res["duration_ms"] == 0


def test_inspect_image_meta_static_png() -> None:
    buf = io.BytesIO()
    img = Image.new("RGB", (2, 2), color="blue")
    img.save(buf, format="PNG")
    buf.seek(0)
    res = _inspect_image_meta(buf)
    assert res == {"animated": False, "duration_ms": 0}


def test_inspect_image_meta_corrupted_stream() -> None:
    stream = io.BytesIO(b"corrupted_garbage_bytes")
    res = _inspect_image_meta(stream)
    assert res == {"animated": False, "duration_ms": 0}
