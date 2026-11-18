"""Bounded ISO-BMFF structural inspection for local Film Studio fixtures."""
from pathlib import Path


def _mp4_structural(path):
    path = Path(path)
    """Read enough ISO-BMFF structure to require audio and video tracks."""
    size = path.stat().st_size
    if size < 512 or size > 160_000_000:
        raise ValueError("MP4 outside allowed size range")
    with path.open("rb") as fd:
        box_types = set()
        moov = b""
        pos = 0
        while pos + 8 <= size:
            fd.seek(pos)
            header = fd.read(16)
            length = int.from_bytes(header[:4], "big")
            name = header[4:8]
            header_size = 8
            if length == 1:
                length = int.from_bytes(header[8:16], "big")
                header_size = 16
            if length == 0:
                length = size - pos
            if length < header_size or pos + length > size:
                raise ValueError("MP4 box boundary invalid")
            box_types.add(name)
            if name == b"moov":
                if length > 2_000_000:
                    raise ValueError("MP4 metadata too large")
                fd.seek(pos + header_size)
                moov = fd.read(length - header_size)
            pos += length
    if not {b"ftyp", b"moov", b"mdat"}.issubset(box_types):
        raise ValueError("MP4 missing expected structural boxes")
    if b"vide" not in moov or b"soun" not in moov:
        raise ValueError("MP4 missing video or audio track")
    return {"container": "mp4", "audio_track_present": True,
            "video_track_present": True, "structure_only": True}

