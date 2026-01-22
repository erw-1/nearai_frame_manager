"""EXIF metadata extraction helpers."""
from datetime import datetime, timedelta, timezone
import os
from typing import Any

import piexif

from .common import decode_exif_text, parse_exif_date, parse_exif_datetime, prune_none

EXIF_TAGS_BY_NAME = {
    ifd_name: {tag_info["name"]: tag_id for tag_id, tag_info in piexif.TAGS[ifd_name].items()}
    for ifd_name in piexif.TAGS
}


def exif_tag_value(exif_dict: dict[str, dict[int, Any]], ifd_name: str, tag_name: str) -> Any:
    """Return an EXIF tag value by name."""
    tag_id = EXIF_TAGS_BY_NAME.get(ifd_name, {}).get(tag_name)
    if tag_id is None:
        return None
    return exif_dict.get(ifd_name, {}).get(tag_id)


def rational_to_float(value: Any) -> float | None:
    """Convert a rational or numeric EXIF value to float."""
    if isinstance(value, tuple) and len(value) == 2:
        numerator, denominator = value
        if denominator == 0:
            return None
        return numerator / denominator
    if isinstance(value, (int, float)):
        return float(value)
    return None


def exif_to_int(value: Any) -> int | None:
    """Convert an EXIF value to int when possible."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = decode_exif_text(value)
    if not text:
        return None
    try:
        return int(text.strip())
    except ValueError:
        return None


def gps_to_degrees(value: Any, ref: Any) -> float | None:
    """Convert EXIF GPS coordinates to signed degrees."""
    if not value or not ref:
        return None
    try:
        degrees = rational_to_float(value[0])
        minutes = rational_to_float(value[1])
        seconds = rational_to_float(value[2])
    except (IndexError, TypeError):
        return None
    if degrees is None or minutes is None or seconds is None:
        return None
    coord = degrees + minutes / 60.0 + seconds / 3600.0
    ref_text = decode_exif_text(ref)
    if ref_text and ref_text.upper() in ("S", "W"):
        coord *= -1.0
    return coord


def gps_datetime_utc(gps_date: Any, gps_time: Any) -> str | None:
    """Build a UTC ISO timestamp from GPS date/time EXIF tags."""
    date_code = parse_exif_date(gps_date)
    if not date_code or not isinstance(gps_time, (list, tuple)) or len(gps_time) != 3:
        return None
    hours = rational_to_float(gps_time[0])
    minutes = rational_to_float(gps_time[1])
    seconds = rational_to_float(gps_time[2])
    if hours is None or minutes is None or seconds is None:
        return None
    try:
        base = datetime.strptime(date_code, "%Y%m%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return (base + timedelta(hours=hours, minutes=minutes, seconds=seconds)).isoformat().replace("+00:00", "Z")


def extract_exif_metadata(img_path: str) -> tuple[str, dict[str, Any]]:
    """Extract EXIF metadata and derived fields from an image."""
    try:
        exif_dict = piexif.load(img_path)
    except (piexif.InvalidImageDataError, ValueError, OSError):
        exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "Interop": {}}
    gps_lat = gps_to_degrees(
        exif_tag_value(exif_dict, "GPS", "GPSLatitude"),
        exif_tag_value(exif_dict, "GPS", "GPSLatitudeRef"),
    )
    gps_lon = gps_to_degrees(
        exif_tag_value(exif_dict, "GPS", "GPSLongitude"),
        exif_tag_value(exif_dict, "GPS", "GPSLongitudeRef"),
    )
    gps_alt = rational_to_float(exif_tag_value(exif_dict, "GPS", "GPSAltitude"))
    gps_alt_ref = exif_tag_value(exif_dict, "GPS", "GPSAltitudeRef")
    if isinstance(gps_alt_ref, bytes):
        gps_alt_ref = gps_alt_ref[0] if gps_alt_ref else None
    gps_alt_ref_label = {0: "above_sea_level", 1: "below_sea_level"}.get(gps_alt_ref)
    gps_timestamp = gps_datetime_utc(
        exif_tag_value(exif_dict, "GPS", "GPSDateStamp"),
        exif_tag_value(exif_dict, "GPS", "GPSTimeStamp"),
    )
    dt_text = parse_exif_datetime(
        exif_tag_value(exif_dict, "Exif", "DateTimeOriginal")
        or exif_tag_value(exif_dict, "Exif", "DateTimeDigitized")
        or exif_tag_value(exif_dict, "0th", "DateTime")
    )
    camera = {
        "make": decode_exif_text(exif_tag_value(exif_dict, "0th", "Make")),
        "model": decode_exif_text(exif_tag_value(exif_dict, "0th", "Model")),
        "serial_number": decode_exif_text(
            exif_tag_value(exif_dict, "Exif", "BodySerialNumber")
            or exif_tag_value(exif_dict, "Exif", "SerialNumber")
            or exif_tag_value(exif_dict, "0th", "SerialNumber")
        ),
        "software": decode_exif_text(exif_tag_value(exif_dict, "0th", "Software")),
        "focal_length_mm": rational_to_float(exif_tag_value(exif_dict, "Exif", "FocalLength")),
        "focal_length_35mm": exif_to_int(exif_tag_value(exif_dict, "Exif", "FocalLengthIn35mmFilm")),
        "f_number": rational_to_float(exif_tag_value(exif_dict, "Exif", "FNumber")),
    }
    gps_date_code = parse_exif_date(exif_tag_value(exif_dict, "GPS", "GPSDateStamp"))
    dt_date_code = parse_exif_date(dt_text.split("T")[0].split(" ")[0]) if dt_text else None
    date_code = gps_date_code or dt_date_code
    if not date_code or len(date_code) != 8 or not date_code.isdigit():
        date_code = datetime.fromtimestamp(os.path.getmtime(img_path), tz=timezone.utc).strftime("%Y%m%d")
    derived = {
        "datetime_original": dt_text,
        "gps": {
            "latitude_deg": gps_lat,
            "longitude_deg": gps_lon,
            "altitude_m": gps_alt,
            "altitude_ref": gps_alt_ref_label,
            "timestamp_utc": gps_timestamp,
        },
        "camera": camera,
    }
    return date_code, prune_none(derived)


def extract_camera_model(img_path: str) -> str | None:
    """Return the camera model from EXIF metadata."""
    try:
        exif_dict = piexif.load(img_path)
    except (piexif.InvalidImageDataError, ValueError, OSError):
        return None
    return decode_exif_text(exif_tag_value(exif_dict, "0th", "Model"))
