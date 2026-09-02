"""Audio quality scoring: used to decide which duplicate copy survives."""

import os

import mutagen

# Rough fidelity tiers: lossless > modern lossy > mp3-era lossy.
FORMAT_TIER = {
    ".flac": 6, ".ape": 6, ".wv": 6, ".alac": 6,
    ".aiff": 5, ".aif": 5, ".wav": 5,
    ".opus": 4, ".ogg": 4, ".oga": 4,
    ".m4a": 3, ".aac": 3, ".mpc": 3, ".m4b": 3,
    ".mp3": 2, ".wma": 1, ".asf": 1,
}


def score(path: str) -> tuple:
    """Comparable quality tuple for one audio file. Higher is better."""
    ext = os.path.splitext(path)[1].lower()
    tier = FORMAT_TIER.get(ext, 0)
    bitrate = sample_rate = bits = 0
    try:
        m = mutagen.File(path)
        if m is not None:
            info = m.info
            bitrate = int(getattr(info, "bitrate", 0) or 0)
            sample_rate = int(getattr(info, "sample_rate", 0) or 0)
            bits = int(getattr(info, "bits_per_sample", 0) or 0)
    except Exception:
        pass
    return (tier, bits, sample_rate, bitrate)


def score_files(paths: list[str]) -> tuple:
    """Quality of a unit/album = its best file."""
    best = (0, 0, 0, 0)
    for p in paths:
        s = score(p)
        if s > best:
            best = s
    return best


def better(new_paths: list[str], old_paths: list[str]) -> bool:
    """True only if the new copy is strictly better than the old one."""
    return score_files(new_paths) > score_files(old_paths)


def describe(s: tuple) -> str:
    tier, bits, rate, br = s
    return f"tier{tier}/{bits or '-'}bit/{rate or '-'}Hz/{br // 1000 if br else '-'}kbps"
