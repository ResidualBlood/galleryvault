"""Fast media duration probes.

Pure helpers used by the gallery page-meta endpoint. They intentionally avoid
FastAPI/SQLAlchemy imports so they can be imported and unit-tested in isolation;
``galleries`` re-exports them for existing callers. Pillow is only needed for the
slow path of ``_inspect_image_meta``.
"""

from __future__ import annotations

import io
import logging
from typing import Any, BinaryIO

from PIL import Image, ImageSequence

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


def _fast_parse_webp_duration(stream: BinaryIO) -> int | None:
    try:
        start_pos = stream.tell()
    except (OSError, AttributeError, io.UnsupportedOperation):
        start_pos = 0

    try:
        header = stream.read(12)
        if len(header) < 12 or header[:4] != b"RIFF" or header[8:12] != b"WEBP":
            return None

        total_duration = 0
        anmf_count = 0

        while True:
            chunk_header = stream.read(8)
            if len(chunk_header) < 8:
                break
            fourcc = chunk_header[:4]
            chunk_size = int.from_bytes(chunk_header[4:8], "little")
            padding = chunk_size % 2

            if fourcc == b"ANMF":
                if chunk_size < 16:
                    return None
                payload_head = stream.read(16)
                if len(payload_head) < 16:
                    return None
                dur = int.from_bytes(payload_head[12:15], "little")
                if dur <= 0:
                    dur = 100
                total_duration += dur
                anmf_count += 1
                skip = (chunk_size - 16) + padding
            else:
                skip = chunk_size + padding

            if not _skip_stream_bytes(stream, skip):
                break

        if anmf_count > 0:
            return min(total_duration, 120000)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.debug("Fast WebP parsing failed: %s", exc)
        return None
    finally:
        try:
            stream.seek(start_pos)
        except (OSError, AttributeError, io.UnsupportedOperation):
            try:
                stream.seek(0)
            except (OSError, AttributeError, io.UnsupportedOperation):
                pass


def _inspect_image_meta(stream: BinaryIO) -> dict[str, Any]:
    try:
        start_pos = 0
        try:
            start_pos = stream.tell()
        except (OSError, AttributeError, io.UnsupportedOperation):
            start_pos = 0

        try:
            fast_duration = _fast_parse_webp_duration(stream)
            if fast_duration is not None:
                return {"animated": True, "duration_ms": min(fast_duration, 120000)}
        except Exception as exc:  # noqa: BLE001
            logger.debug("Fast WebP parsing failed, fallback to GIF: %s", exc)
        finally:
            try:
                stream.seek(start_pos)
            except (OSError, AttributeError, io.UnsupportedOperation):
                try:
                    stream.seek(0)
                except (OSError, AttributeError, io.UnsupportedOperation):
                    pass

        try:
            fast_duration = _fast_parse_gif_duration(stream)
            if fast_duration is not None:
                return {"animated": True, "duration_ms": min(fast_duration, 120000)}
        except Exception as exc:  # noqa: BLE001
            logger.debug("Fast GIF parsing failed, fallback to Pillow: %s", exc)
        finally:
            try:
                stream.seek(start_pos)
            except (OSError, AttributeError, io.UnsupportedOperation):
                try:
                    stream.seek(0)
                except (OSError, AttributeError, io.UnsupportedOperation):
                    pass

        with Image.open(stream) as img:
            is_animated = bool(getattr(img, "is_animated", False))
            if not is_animated:
                return {"animated": False, "duration_ms": 0}
            is_webp = getattr(img, "format", "") == "WEBP"
            total_duration = 0
            for frame_count, frame in enumerate(ImageSequence.Iterator(img)):
                if frame_count >= 50:
                    break
                if is_webp:
                    frame.load()
                dur = frame.info.get("duration", 100)
                if not isinstance(dur, (int, float)) or dur <= 0:
                    dur = 100
                total_duration += int(dur)
            return {"animated": True, "duration_ms": min(total_duration, 120000)}
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed to inspect image meta: %s", exc)
        return {"animated": False, "duration_ms": 0}
    finally:
        try:
            stream.close()
        except OSError:
            pass
