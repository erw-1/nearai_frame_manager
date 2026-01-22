"""Common helpers shared across modules."""
from datetime import datetime, timedelta, timezone
import csv
import os
import re
from typing import Any

GPS_EPOCH = datetime(1980, 1, 6, tzinfo=timezone.utc)
UNIX_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def normalize_token(value: str, label: str) -> str:
    """Return a cleaned token suitable for IDs; raise ValueError on empty."""
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "", value.strip())
    if not cleaned:
        raise ValueError(f"{label} cannot be empty.")
    return cleaned


def normalize_header_name(value: str) -> str:
    """Normalize a CSV header name for matching."""
    return re.sub(r"[^a-z0-9]+", "", value.strip().lower())


def normalize_image_key(value: str) -> str:
    """Normalize an image filename into a lookup key."""
    return os.path.splitext(os.path.basename(value.strip()))[0].lower()


def prune_none(value: Any) -> Any:
    """Recursively remove None values and empty containers."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, sub in value.items():
            sub = prune_none(sub)
            if sub is None:
                continue
            if isinstance(sub, dict) and not sub:
                continue
            if isinstance(sub, list) and not sub:
                continue
            out[key] = sub
        return out
    if isinstance(value, list):
        out_list = []
        for item in value:
            item = prune_none(item)
            if item is None:
                continue
            if isinstance(item, dict) and not item:
                continue
            if isinstance(item, list) and not item:
                continue
            out_list.append(item)
        return out_list
    return value


def parse_float(value: Any) -> float | None:
    """Parse a float from a value, returning None on failure."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


def seconds_to_utc(seconds: float, epoch: str) -> str:
    """Convert epoch seconds (gps/unix) to ISO-8601 UTC string."""
    base = GPS_EPOCH if epoch == "gps" else UNIX_EPOCH
    return (base + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


def decode_exif_text(value: Any) -> str | None:
    """Decode EXIF bytes/strings into clean text."""
    if value is None:
        return None
    if isinstance(value, bytes):
        text = value.decode(errors="ignore")
    elif isinstance(value, str):
        text = value
    else:
        return None
    text = re.sub(r"[\x00-\x1f\x7f]", "", text).strip()
    return text or None


def parse_exif_date(value: Any) -> str | None:
    """Parse an EXIF date string into YYYYMMDD."""
    text = decode_exif_text(value)
    if not text:
        return None
    for fmt in ("%Y:%m:%d", "%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y%m%d")
        except ValueError:
            continue
    return None


def parse_exif_datetime(value: Any) -> str | None:
    """Parse an EXIF datetime string into ISO format when possible."""
    text = decode_exif_text(value)
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
        return parsed.isoformat().replace("+00:00", "Z")
    except ValueError:
        pass
    cleaned = text.replace("T", " ")
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(cleaned, fmt).isoformat()
        except ValueError:
            continue
    return cleaned


def date_from_folder_name(folder_name: str) -> str | None:
    """Extract a YYYYMMDD date from a folder name."""
    for match in re.finditer(r"\d{8}", folder_name):
        candidate = match.group(0)
        try:
            datetime.strptime(candidate, "%Y%m%d")
        except ValueError:
            continue
        return candidate
    return None


def ensure_dirs(*paths: str) -> None:
    """Create directories if they do not exist."""
    for path in paths:
        if path:
            os.makedirs(path, exist_ok=True)


def sniff_csv_dialect(sample: str) -> csv.Dialect:
    """Return a CSV dialect for the given sample string."""
    try:
        return csv.Sniffer().sniff(sample, delimiters=",\t;")
    except csv.Error:
        return csv.excel_tab if "\t" in sample else csv.excel


def read_csv_headers(path: str) -> list[str] | None:
    """Read the header row from a CSV file, or None if unreadable."""
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as handle:
            sample = handle.read(2048)
            handle.seek(0)
            dialect = sniff_csv_dialect(sample)
            reader = csv.reader(handle, dialect=dialect)
            return next(reader, [])
    except OSError:
        return None
