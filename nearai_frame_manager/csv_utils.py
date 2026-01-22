"""CSV parsing helpers for pose data."""
import os
import re
from typing import Any

from .common import (
    normalize_header_name,
    normalize_image_key,
    parse_float,
    read_csv_headers,
    seconds_to_utc,
    sniff_csv_dialect,
)
from .constants import POSE_CSV_FIELD_ALIASES
from .models import PoseLookup


def build_pose_csv_column_map(fieldnames: list[str]) -> dict[str, str]:
    """Map canonical pose fields to CSV header names."""
    normalized = {normalize_header_name(name): name for name in fieldnames if name}
    mapping: dict[str, str] = {}
    for key, aliases in POSE_CSV_FIELD_ALIASES.items():
        for alias in aliases:
            alias_key = normalize_header_name(alias)
            if alias_key in normalized:
                mapping[key] = normalized[alias_key]
                break
    return mapping


def load_pose_csv(path: str, epoch: str) -> PoseLookup:
    """Load a pose CSV into a mapping keyed by normalized image name."""
    import csv

    if epoch not in ("gps", "unix"):
        raise ValueError("pose-epoch must be 'gps' or 'unix'.")
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        sample = handle.read(2048)
        handle.seek(0)
        dialect = sniff_csv_dialect(sample)
        reader = csv.DictReader(handle, dialect=dialect)
        if not reader.fieldnames:
            raise ValueError("Pose CSV is missing headers.")
        column_map = build_pose_csv_column_map(list(reader.fieldnames))
        if "file_name" not in column_map:
            raise ValueError("Pose CSV is missing a file_name column.")
        poses: PoseLookup = {}
        for row in reader:
            raw_name = (row.get(column_map["file_name"]) or "").strip()
            if not raw_name:
                continue
            gps_seconds = parse_float(row.get(column_map.get("gps_seconds", "")))
            timestamp = seconds_to_utc(gps_seconds, epoch) if gps_seconds is not None else None
            poses[normalize_image_key(raw_name)] = {
                "file_name": raw_name,
                "gps_seconds": gps_seconds,
                "timestamp": timestamp,
                "gps_latitude": parse_float(row.get(column_map.get("latitude", ""))),
                "gps_longitude": parse_float(row.get(column_map.get("longitude", ""))),
                "gps_altitude_m": parse_float(row.get(column_map.get("altitude", ""))),
                "heading_deg": parse_float(row.get(column_map.get("heading", ""))),
                "pitch_deg": parse_float(row.get(column_map.get("pitch", ""))),
                "roll_deg": parse_float(row.get(column_map.get("roll", ""))),
            }
        return poses


def csv_has_pose_headers(path: str) -> bool:
    """Return True if a CSV file looks like a pose file."""
    headers = read_csv_headers(path)
    if not headers:
        return False
    column_map = build_pose_csv_column_map(list(headers))
    return "file_name" in column_map


def depth_from_root(root: str, path: str) -> int:
    """Return directory depth of a path relative to a root."""
    rel = os.path.relpath(path, root)
    if rel == os.curdir:
        return 0
    return rel.count(os.sep)


def find_pose_csv_path(folder: str) -> str | None:
    """Locate the closest pose CSV under a folder."""
    candidates: list[str] = []
    for root, _dirs, files in os.walk(folder):
        for file in files:
            if not file.lower().endswith(".csv"):
                continue
            if re.match(r"^s\d{3}_trajectory\.csv$", file.lower()):
                continue
            candidates.append(os.path.join(root, file))
    candidates.sort(key=lambda path: (depth_from_root(folder, path), path.lower()))
    for candidate in candidates:
        if csv_has_pose_headers(candidate):
            return os.path.abspath(candidate)
    return None
