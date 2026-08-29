#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NovelAI stealth_pngcomp: alpha-channel LSB payload used by NAI / viewer.html.

The payload is not a PNG text chunk. It is packed into the least-significant
bit of the alpha channel, column-major (x outer, y inner), as:

    signature  "stealth_pngcomp"   (15 bytes, MSB-first bits)
    length     uint32 bit-length   of the compressed payload
    data       gzip-compressed JSON

PNG and lossless WebP with alpha both preserve those LSBs. JPEG / lossy WebP
do not. Existence is decided by the 120-bit signature alone (2^-120).
"""

from __future__ import annotations

import logging
import os
import struct
import zlib
from typing import Optional

import numpy as np
from PIL import Image

logger = logging.getLogger('manga_translator')

STEALTH_PNGCOMP_SIG = b'stealth_pngcomp'
STEALTH_PNGCOMP_SIG_BITS = tuple(
    (byte >> (7 - bit)) & 1
    for byte in STEALTH_PNGCOMP_SIG
    for bit in range(8)
)
_PNG_MAGIC = b'\x89PNG\r\n\x1a\n'
_STEALTH_SAVE_FORMATS = {'PNG', 'WEBP'}


def sniff_stealth_container(path: str) -> Optional[str]:
    """Return 'png' or 'webp' from magic bytes, ignoring the file extension."""
    try:
        with open(path, 'rb') as handle:
            magic = handle.read(12)
    except OSError:
        return None
    if magic.startswith(_PNG_MAGIC):
        return 'png'
    if magic[:4] == b'RIFF' and magic[8:12] == b'WEBP':
        return 'webp'
    return None


def has_stealth_pngcomp(path: Optional[str]) -> bool:
    """Cheap existence check. Does not gzip-decompress or parse JSON."""
    if not path:
        return False
    kind = sniff_stealth_container(path)
    if kind == 'png':
        result = _png_has_stealth_signature(path)
        if result is not None:
            return result
        return _pil_has_stealth_signature(path)
    if kind == 'webp':
        if _webp_header_has_alpha(path) is False:
            return False
        return _pil_has_stealth_signature(path)
    return False


def extract_stealth_pngcomp_payload(path: Optional[str]) -> Optional[bytes]:
    """Return the gzip-compressed payload bytes, or None."""
    if not path or not has_stealth_pngcomp(path):
        return None
    try:
        with Image.open(path) as image:
            image.load()
            return extract_stealth_pngcomp_payload_from_image(image)
    except Exception as exc:
        logger.warning(f"Failed to extract stealth_pngcomp from {path}: {exc}")
        return None


def extract_stealth_pngcomp_payload_from_image(image: Image.Image) -> Optional[bytes]:
    bits = _column_major_alpha_lsbs(image)
    if bits is None:
        return None
    sig_len = len(STEALTH_PNGCOMP_SIG_BITS)
    if bits.size < sig_len + 32:
        return None
    if not np.array_equal(bits[:sig_len], STEALTH_PNGCOMP_SIG_BITS):
        return None
    length = int(''.join(str(int(b)) for b in bits[sig_len:sig_len + 32]), 2)
    if length <= 0 or length % 8 != 0:
        return None
    end = sig_len + 32 + length
    if bits.size < end:
        return None
    data_bits = bits[sig_len + 32:end]
    return np.packbits(data_bits, bitorder='big').tobytes()


def embed_stealth_pngcomp(image: Image.Image, payload: bytes) -> Optional[Image.Image]:
    """Return a new RGBA image with payload written into alpha LSBs."""
    if image is None or not payload:
        return None
    rgba = image.convert('RGBA')
    if rgba is image:
        rgba = image.copy()
    alpha = np.array(rgba.getchannel('A'), dtype=np.uint8, copy=True)
    height, width = alpha.shape
    bitstream = _payload_to_bits(payload)
    if bitstream.size > width * height:
        logger.warning(
            f"stealth_pngcomp payload does not fit in {width}x{height} "
            f"({bitstream.size} bits needed)"
        )
        if rgba is not image:
            rgba.close()
        return None
    # Column-major: flatten as (x, y)
    col_major = alpha.T.ravel()
    col_major[:bitstream.size] = (col_major[:bitstream.size] & 0xFE) | bitstream
    new_alpha = col_major.reshape(width, height).T
    rgba.putalpha(Image.fromarray(new_alpha, mode='L'))
    return rgba


def resolve_stealth_pngcomp_payload(*paths: Optional[str]) -> Optional[bytes]:
    """Return the first stealth_pngcomp payload found among the given files."""
    seen = set()
    for path in paths:
        if not path:
            continue
        try:
            normalized = os.path.normcase(os.path.normpath(path))
        except Exception:
            normalized = path
        if normalized in seen:
            continue
        seen.add(normalized)
        if not os.path.isfile(path):
            continue
        payload = extract_stealth_pngcomp_payload(path)
        if payload:
            return payload
    return None


def resolve_stealth_pngcomp_for_image(
    source_path: Optional[str],
    *,
    inpainted_only: bool = False,
) -> Optional[bytes]:
    """Resolve a stealth_pngcomp payload for a page.

    Normal saves read the original, then the cleanup image.
    TXT import (`inpainted_only=True`) reads only the cleanup image and
    gives up if that file has no payload.
    """
    if not source_path:
        return None
    inpainted_path = None
    try:
        from .path_manager import find_inpainted_path
        inpainted_path = find_inpainted_path(source_path)
    except Exception:
        inpainted_path = None
    if inpainted_only:
        return resolve_stealth_pngcomp_payload(inpainted_path)
    return resolve_stealth_pngcomp_payload(source_path, inpainted_path)


def apply_stealth_pngcomp_for_save(
    image: Image.Image,
    target_format: str,
    *,
    payload: Optional[bytes] = None,
    stealth_source_path: Optional[str] = None,
) -> tuple[Image.Image, Optional[Image.Image], dict]:
    """Embed payload when the destination format can keep alpha LSBs.

    Returns (image_to_save, owned_image_or_none, extra_save_kwargs).
    """
    extra = {}
    if target_format not in _STEALTH_SAVE_FORMATS:
        return image, None, extra
    if payload is None:
        payload = extract_stealth_pngcomp_payload(stealth_source_path)
    if not payload:
        return image, None, extra
    embedded = embed_stealth_pngcomp(image, payload)
    if embedded is None:
        return image, None, extra
    if target_format == 'WEBP':
        extra['lossless'] = True
    logger.debug(f"Re-embedded stealth_pngcomp into {target_format} output ({len(payload)} bytes)")
    return embedded, embedded, extra


def _payload_to_bits(payload: bytes) -> np.ndarray:
    sig_bits = np.fromiter(STEALTH_PNGCOMP_SIG_BITS, dtype=np.uint8)
    length_bits = np.unpackbits(
        np.array([(len(payload) * 8 >> (24 - 8 * i)) & 0xFF for i in range(4)], dtype=np.uint8),
        bitorder='big',
    )
    data_bits = np.unpackbits(np.frombuffer(payload, dtype=np.uint8), bitorder='big')
    return np.concatenate([sig_bits, length_bits, data_bits])


def _column_major_alpha_lsbs(image: Image.Image) -> Optional[np.ndarray]:
    alpha = _alpha_array(image)
    if alpha is None:
        return None
    return (alpha.T & 1).ravel()


def _alpha_array(image: Image.Image) -> Optional[np.ndarray]:
    if image.mode in ('RGBA', 'LA'):
        return np.asarray(image.getchannel('A'), dtype=np.uint8)
    if image.mode == 'RGBa':
        converted = image.convert('RGBA')
        try:
            return np.asarray(converted.getchannel('A'), dtype=np.uint8)
        finally:
            if converted is not image:
                converted.close()
    return None


def _pil_has_stealth_signature(path: str) -> bool:
    try:
        with Image.open(path) as image:
            image.load()
            bits = _column_major_alpha_lsbs(image)
    except Exception:
        return False
    if bits is None or bits.size < len(STEALTH_PNGCOMP_SIG_BITS):
        return False
    return bool(np.array_equal(bits[:len(STEALTH_PNGCOMP_SIG_BITS)], STEALTH_PNGCOMP_SIG_BITS))


def _png_has_stealth_signature(path: str) -> Optional[bool]:
    """Stream-decode only the first column prefix of a non-interlaced 8-bit PNG.

    Returns True/False, or None to fall back to PIL (interlace, odd bit depth, etc.).
    """
    try:
        ihdr, idat = _read_png_idat(path)
    except Exception:
        return None
    if ihdr is None or not idat:
        return None
    if ihdr['interlace']:
        return None
    if ihdr['bit'] != 8 or ihdr['color'] not in (4, 6):
        return False
    width, height = ihdr['w'], ihdr['h']
    n_bits = len(STEALTH_PNGCOMP_SIG_BITS)
    if width * height < n_bits:
        return False
    bpp = 2 if ihdr['color'] == 4 else 4
    stride = 1 + width * bpp
    need_rows = n_bits if height >= n_bits else height
    if height < n_bits:
        return None
    try:
        raw = _inflate_png_prefix(idat, need_rows * stride)
    except Exception:
        return None
    if raw is None or len(raw) < need_rows * stride:
        return None
    prev = [0] * bpp
    src = 0
    for i in range(need_rows):
        filter_type = raw[src]
        recon = [0] * bpp
        for k in range(bpp):
            up = prev[k]
            x = raw[src + 1 + k]
            if filter_type == 0:
                val = x
            elif filter_type == 1:
                val = x
            elif filter_type == 2:
                val = (x + up) & 255
            elif filter_type == 3:
                val = (x + (up // 2)) & 255
            elif filter_type == 4:
                val = (x + _paeth(0, up, 0)) & 255
            else:
                return None
            recon[k] = val
        if (recon[-1] & 1) != STEALTH_PNGCOMP_SIG_BITS[i]:
            return False
        prev = recon
        src += stride
    return True


def _read_png_idat(path: str) -> tuple[Optional[dict], bytes]:
    with open(path, 'rb') as handle:
        if handle.read(8) != _PNG_MAGIC:
            return None, b''
        ihdr = None
        idat = bytearray()
        while True:
            header = handle.read(8)
            if len(header) < 8:
                break
            length, ctype = struct.unpack('>I4s', header)
            chunk = handle.read(length)
            handle.read(4)
            if ctype == b'IHDR' and length >= 13:
                width, height, bit, color, _comp, _filt, inter = struct.unpack('>IIBBBBB', chunk[:13])
                ihdr = {
                    'w': width,
                    'h': height,
                    'bit': bit,
                    'color': color,
                    'interlace': inter,
                }
            elif ctype == b'IDAT':
                idat.extend(chunk)
            elif ctype == b'IEND':
                break
    return ihdr, bytes(idat)


def _inflate_png_prefix(idat: bytes, need_bytes: int) -> Optional[bytearray]:
    decoder = zlib.decompressobj()
    raw = bytearray()
    offset = 0
    step = 65536
    while offset < len(idat) and len(raw) < need_bytes:
        raw.extend(decoder.decompress(idat[offset:offset + step]))
        offset += step
    if len(raw) < need_bytes:
        raw.extend(decoder.flush())
    return raw


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def _webp_header_has_alpha(path: str) -> Optional[bool]:
    """True/False from VP8X/ALPH, or None if the bitstream must be decoded."""
    try:
        with open(path, 'rb') as handle:
            data = handle.read(128)
    except OSError:
        return None
    if data[:4] != b'RIFF' or data[8:12] != b'WEBP':
        return None
    offset = 12
    saw_vp8x = False
    while offset + 8 <= len(data):
        fourcc = data[offset:offset + 4]
        size = struct.unpack_from('<I', data, offset + 4)[0]
        payload_start = offset + 8
        if fourcc == b'VP8X' and payload_start < len(data):
            saw_vp8x = True
            return bool(data[payload_start] & 0x10)
        if fourcc == b'ALPH':
            return True
        if fourcc == b'VP8 ' and not saw_vp8x:
            return False
        offset += 8 + size + (size & 1)
    return None
