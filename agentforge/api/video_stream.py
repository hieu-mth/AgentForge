"""Strict single-range byte parsing for local Owner MP4 playback.

No multipart ranges or open-ended arbitrary file paths. HTTP handler sends
416 for invalid/unsatisfiable ranges; a regular GET returns the whole file.
"""
import re


class InvalidVideoRange(ValueError):
    pass


def parse_range(header, length):
    if type(length) is not int or length <= 0:
        raise InvalidVideoRange("Empty or invalid MP4")
    if header is None:
        return 0, length - 1, False
    if not isinstance(header, str) or len(header) > 100:
        raise InvalidVideoRange("Invalid range")
    matched = re.fullmatch(r"bytes=(\d*)-(\d*)", header)
    if matched is None:
        raise InvalidVideoRange("Only one byte range supported")
    first, last = matched.groups()
    if not first and not last:
        raise InvalidVideoRange("Empty byte range")
    if not first:
        suffix = int(last)
        if suffix < 1:
            raise InvalidVideoRange("Empty suffix")
        return max(0, length - suffix), length - 1, True
    start = int(first)
    if start >= length:
        raise InvalidVideoRange("Unsatisfiable range")
    end = min(length - 1, int(last)) if last else length - 1
    if end < start:
        raise InvalidVideoRange("Reversed range")
    return start, end, True
