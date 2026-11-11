"""Fast, dependency-free media duration probes.

Pure helpers used by the gallery page-meta endpoint. They intentionally avoid
FastAPI/SQLAlchemy imports so they can be imported and unit-tested in isolation;
``galleries`` re-exports them for existing callers.
"""

from __future__ import annotations

import io
import logging
from typing import BinaryIO

# Keep the pre-split logger name so log records stay attributed to the router.
logger = logging.getLogger("galleryvault.app.routers.galleries")


def _skip_stream_bytes(stream: BinaryIO, num_bytes: int) -> bool:
    if num_bytes <= 0:
        return True
    try:
        stream.seek(num_bytes, 1)
        return True
    except (OSError, AttributeError, io.UnsupportedOperation):
        remaining = num_bytes
        while remaining > 0:
            chunk = stream.read(min(remaining, 65536))
            if not chunk:
                return False
            remaining -= len(chunk)
        return True


def _skip_subblocks(stream: BinaryIO) -> bool:
    subblock_count = 0
    max_subblocks = 100_000
    while subblock_count < max_subblocks:
        subblock_count += 1
        sub_len_b = stream.read(1)
        if not sub_len_b:
            return False
        sub_len = sub_len_b[0]
        if sub_len == 0:
            return True
        if not _skip_stream_bytes(stream, sub_len):
            return False
    return False


def _fast_parse_gif_duration(stream: BinaryIO) -> int | None:
    try:
        start_pos = stream.tell()
    except (OSError, AttributeError, io.UnsupportedOperation):
        start_pos = 0

    try:
        header = stream.read(6)
        if header not in (b"GIF87a", b"GIF89a"):
            return None

        lsd = stream.read(7)
        if len(lsd) < 7:
            return None

        packed = lsd[4]
        if packed & 0x80:
            gct_size = 3 * (1 << ((packed & 0x07) + 1))
            gct = stream.read(gct_size)
            if len(gct) < gct_size:
                return None

        frame_count = 0
        total_duration = 0
        current_gce_delay: int | None = None
        block_count = 0

        while block_count < 10000:
            block_count += 1
            intro = stream.read(1)
            if not intro or intro == b"\x3b":
                break

            if intro == b"\x00":
                continue

            if intro == b"\x21":
                label = stream.read(1)
                if not label:
                    return None
                if label == b"\xf9":
                    size_b = stream.read(1)
                    if not size_b:
                        return None
                    size = size_b[0]
                    gce_data = stream.read(size)
                    if len(gce_data) < size:
                        return None
                    if size >= 4:
                        delay_cs = int.from_bytes(gce_data[1:3], "little")
                        current_gce_delay = 100 if delay_cs <= 1 else delay_cs * 10
                    if not _skip_subblocks(stream):
                        return None
                else:
                    if not _skip_subblocks(stream):
                        return None

            elif intro == b"\x2c":
                desc = stream.read(9)
                if len(desc) < 9:
                    return None
                img_packed = desc[8]
                if img_packed & 0x80:
                    lct_size = 3 * (1 << ((img_packed & 0x07) + 1))
                    lct = stream.read(lct_size)
                    if len(lct) < lct_size:
                        return None

                lzw_min = stream.read(1)
                if not lzw_min:
                    return None

                if not _skip_subblocks(stream):
                    return None

                frame_count += 1
                total_duration += current_gce_delay if current_gce_delay is not None else 100
                current_gce_delay = None
            else:
                return None

        if frame_count >= 2:
            return min(total_duration, 120000)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.debug("Fast GIF parsing failed: %s", exc)
        return None
    finally:
        try:
            stream.seek(start_pos)
        except (OSError, AttributeError, io.UnsupportedOperation):
            try:
                stream.seek(0)
            except (OSError, AttributeError, io.UnsupportedOperation):
                pass
