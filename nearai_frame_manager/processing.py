"""Core processing for acquisition outputs."""
import os
import shutil
from typing import Any

from .common import normalize_image_key, parse_exif_date, parse_float, prune_none, ensure_dirs
from .constants import POSE_DATA_FIELDS
from .exif_utils import extract_exif_metadata
from .io_utils import copy_lidar_assets, write_json, write_trajectory_csv
from .models import PoseLookup, Record


def record_sort_key(record: Record) -> tuple[int, float, str]:
    """Sort key: prefer CSV GPS time, then file mtime."""
    csv_pose = record.get("csv_pose")
    if csv_pose and csv_pose.get("gps_seconds") is not None:
        return (0, float(csv_pose["gps_seconds"]), record["src"])
    return (1, record["mtime"], record["src"])


def choose_acquisition_date(default_date: str, csv_pose: dict[str, Any] | None) -> str:
    """Pick acquisition date based on CSV timestamp override when available."""
    if csv_pose and csv_pose.get("timestamp"):
        csv_date = parse_exif_date(str(csv_pose["timestamp"]).split("T")[0].split(" ")[0])
        if csv_date:
            return csv_date
    return default_date


def apply_csv_overrides(derived: dict[str, Any], csv_pose: dict[str, Any] | None) -> dict[str, Any]:
    """Overlay CSV pose values onto EXIF-derived metadata."""
    if not csv_pose:
        return derived
    gps_info = derived.get("gps", {})
    for gps_key, csv_key in (
        ("latitude_deg", "gps_latitude"),
        ("longitude_deg", "gps_longitude"),
        ("altitude_m", "gps_altitude_m"),
    ):
        if csv_pose.get(csv_key) is not None:
            gps_info[gps_key] = csv_pose[csv_key]
    if csv_pose.get("timestamp") is not None:
        gps_info["timestamp_utc"] = csv_pose["timestamp"]
    derived["gps"] = prune_none(gps_info)
    return derived


def build_records(image_entries: list[dict[str, Any]], pose_lookup: PoseLookup | None) -> list[Record]:
    """Build record dictionaries from image entries and optional pose data."""
    records: list[Record] = []
    for entry in image_entries:
        path = entry["path"]
        csv_pose = pose_lookup.get(normalize_image_key(path)) if pose_lookup else None
        acquisition_date, derived = extract_exif_metadata(path)
        derived = apply_csv_overrides(derived, csv_pose)
        acquisition_date = choose_acquisition_date(acquisition_date, csv_pose)
        records.append(
            {
                "src": path,
                "ext": os.path.splitext(path)[1].lower(),
                "original_name": os.path.basename(path),
                "acquisition_date": acquisition_date,
                "derived": derived,
                "mtime": entry["mtime"],
                "csv_pose": csv_pose,
            }
        )
    return records


def build_pose_entry(info: Record, frame_index: int, image_name: str) -> dict[str, Any]:
    """Build a pose CSV row for a frame."""
    derived = info["derived"]
    gps_info = derived.get("gps", {})
    csv_pose = info.get("csv_pose") or {}
    timestamp = csv_pose.get("timestamp") or gps_info.get("timestamp_utc") or derived.get("datetime_original")
    return {
        "frame_index": frame_index,
        "image_name": image_name,
        "timestamp": timestamp,
        "gps_latitude": gps_info.get("latitude_deg"),
        "gps_longitude": gps_info.get("longitude_deg"),
        "gps_altitude_m": gps_info.get("altitude_m"),
        "heading_deg": csv_pose.get("heading_deg"),
        "pitch_deg": csv_pose.get("pitch_deg"),
        "roll_deg": csv_pose.get("roll_deg"),
    }


def pose_has_data(entry: dict[str, Any]) -> bool:
    """Return True if any pose fields are populated."""
    for key in POSE_DATA_FIELDS:
        value = entry.get(key)
        if value is not None and value != "":
            return True
    return False


def build_annotation_payload(
    info: Record,
    acquisition_id: str,
    sequence_id: str,
    sensor_id: str,
    frame_index: int,
) -> dict[str, Any]:
    """Build the annotation JSON payload for a single frame."""
    derived = info["derived"]
    gps_info = derived.get("gps")
    csv_pose = info.get("csv_pose") or {}
    payload = {
        "previous_name": info["original_name"],
        "acquisition_id": acquisition_id,
        "sequence_id": sequence_id,
        "sensor_id": sensor_id,
        "frame_index": frame_index,
        "capture": {
            "datetime_original": derived.get("datetime_original"),
            "gps_timestamp_utc": gps_info.get("timestamp_utc") if gps_info else None,
        },
        "gps": gps_info,
        "pose": {
            "source": "csv" if info.get("csv_pose") else None,
            "timestamp": csv_pose.get("timestamp"),
            "gps_seconds": csv_pose.get("gps_seconds"),
            "gps_latitude": csv_pose.get("gps_latitude"),
            "gps_longitude": csv_pose.get("gps_longitude"),
            "gps_altitude_m": csv_pose.get("gps_altitude_m"),
            "heading_deg": csv_pose.get("heading_deg"),
            "pitch_deg": csv_pose.get("pitch_deg"),
            "roll_deg": csv_pose.get("roll_deg"),
        },
    }
    return prune_none(payload)


def build_intrinsics(records: list[Record], sensor_id: str) -> dict[str, Any] | None:
    """Build an intrinsics JSON payload from the first available camera data."""
    for record in records:
        camera = record["derived"].get("camera", {})
        if not camera:
            continue
        intrinsics = {
            "sensor_id": sensor_id,
            "camera_make": camera.get("make"),
            "camera_model": camera.get("model"),
            "serial_number": camera.get("serial_number"),
            "software": camera.get("software"),
            "focal_length_mm": camera.get("focal_length_mm"),
            "focal_length_35mm": camera.get("focal_length_35mm"),
            "f_number": camera.get("f_number"),
        }
        intrinsics = prune_none(intrinsics)
        if len(intrinsics) > 1:
            return intrinsics
    return None


def build_coordinate_systems(records: list[Record]) -> dict[str, Any] | None:
    """Build coordinate system metadata from GPS samples."""
    for record in records:
        gps_info = record["derived"].get("gps")
        if not gps_info:
            continue
        if gps_info.get("latitude_deg") is None or gps_info.get("longitude_deg") is None:
            continue
        position: dict[str, Any] = {
            "reference": "WGS84",
            "epsg": 4326,
            "units": "degrees",
            "altitude_units": "meters",
        }
        if gps_info.get("altitude_ref"):
            position["altitude_reference"] = gps_info["altitude_ref"]
        return {"position": position, "source": "EXIF GPS"}
    return None


def build_geojson_track(
    rows: list[dict[str, Any]],
    acquisition_id: str,
    sequence_id: str,
    sensor_id: str,
) -> dict[str, Any] | None:
    """Build a GeoJSON LineString for a sequence trajectory."""
    positions: list[tuple[float, float, float | None]] = []
    alt_count = 0
    for row in rows:
        lat = parse_float(row.get("gps_latitude"))
        lon = parse_float(row.get("gps_longitude"))
        alt = parse_float(row.get("gps_altitude_m"))
        if lat is None or lon is None:
            continue
        positions.append((lon, lat, alt))
        if alt is not None:
            alt_count += 1
    if len(positions) < 2:
        return None
    include_alt = alt_count == len(positions)
    coordinates: list[list[float]] = []
    for lon, lat, alt in positions:
        if include_alt and alt is not None:
            coordinates.append([lon, lat, alt])
        else:
            coordinates.append([lon, lat])
    properties: dict[str, Any] = {
        "acquisition_id": acquisition_id,
        "sequence_id": sequence_id,
        "sensor_id": sensor_id,
        "point_count": len(coordinates),
    }
    if include_alt:
        properties["altitude_units"] = "meters"
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": properties,
                "geometry": {
                    "type": "LineString",
                    "coordinates": coordinates,
                },
            }
        ],
    }


def sequence_ids(index: int, max_per_seq: int) -> tuple[str, str, int]:
    """Return (sequence_id, frame_id, frame_index) for a 1-based record index."""
    sequence_index = (index - 1) // max_per_seq + 1
    frame_index = (index - 1) % max_per_seq + 1
    sequence_id = f"S{sequence_index:03d}"
    frame_id = f"{frame_index:06d}"
    return sequence_id, frame_id, frame_index


def process_acquisition(
    acquisition_id: str,
    records: list[Record],
    sensor_id: str,
    max_per_seq: int,
    output_dir: str,
) -> int:
    """Process and write outputs for a single acquisition."""
    records.sort(key=record_sort_key)
    acquisition_root = os.path.join(output_dir, acquisition_id)
    images_root = os.path.join(acquisition_root, "01_images")
    calibration_root = os.path.join(acquisition_root, "03_calibration")
    annotations_root = os.path.join(acquisition_root, "04_annotations")
    poses_root = os.path.join(acquisition_root, "02_poses")
    ensure_dirs(images_root, calibration_root, annotations_root, poses_root)

    copied = 0
    poses_by_sequence: dict[str, list[dict[str, Any]]] = {}
    sequences_with_pose: set[str] = set()
    sequence_dirs: dict[str, tuple[str, str]] = {}
    current_sequence: str | None = None
    current_count = 0

    coordinate_systems = build_coordinate_systems(records)
    if coordinate_systems:
        write_json(os.path.join(poses_root, "coordinate_systems.json"), coordinate_systems)

    intrinsics = build_intrinsics(records, sensor_id)
    if intrinsics:
        write_json(os.path.join(calibration_root, "intrinsics.json"), intrinsics)

    for idx, info in enumerate(records, start=1):
        sequence_id, frame_id, frame_index = sequence_ids(idx, max_per_seq)

        if current_sequence and sequence_id != current_sequence:
            print(f"Sequence {current_sequence} done ({current_count} images).")
            current_count = 0
        current_sequence = sequence_id

        seq_dirs = sequence_dirs.get(sequence_id)
        if not seq_dirs:
            seq_img_dir = os.path.join(images_root, sequence_id)
            seq_ann_dir = os.path.join(annotations_root, sequence_id)
            ensure_dirs(seq_img_dir, seq_ann_dir)
            sequence_dirs[sequence_id] = (seq_img_dir, seq_ann_dir)
        else:
            seq_img_dir, seq_ann_dir = seq_dirs

        new_base = f"{acquisition_id}_{sequence_id}_{sensor_id}_{frame_id}"
        dest_path = os.path.join(seq_img_dir, f"{new_base}{info['ext']}")
        annotation_path = os.path.join(seq_ann_dir, f"{new_base}.json")
        shutil.copy2(info["src"], dest_path)

        annotation_payload = build_annotation_payload(info, acquisition_id, sequence_id, sensor_id, frame_index)
        write_json(annotation_path, annotation_payload)

        pose_entry = build_pose_entry(info, frame_index, os.path.basename(dest_path))
        poses_by_sequence.setdefault(sequence_id, []).append(pose_entry)
        if pose_has_data(pose_entry):
            sequences_with_pose.add(sequence_id)
        copied += 1
        current_count += 1

    if current_sequence:
        print(f"Sequence {current_sequence} done ({current_count} images).")

    for sequence_id, rows in poses_by_sequence.items():
        if sequence_id not in sequences_with_pose:
            continue
        trajectory_path = os.path.join(poses_root, f"{sequence_id}_trajectory.csv")
        write_trajectory_csv(trajectory_path, rows)
        geojson_payload = build_geojson_track(rows, acquisition_id, sequence_id, sensor_id)
        if geojson_payload:
            geojson_path = os.path.join(poses_root, f"{sequence_id}_trajectory.geojson")
            write_json(geojson_path, geojson_payload)
    return copied


def process_records_by_acquisition(
    records: list[Record],
    region: str,
    sensor_id: str,
    max_per_seq: int,
    output_dir: str,
    lidar_paths: list[str],
) -> tuple[int, int, int]:
    """Group records by acquisition date and process each group."""
    grouped: dict[str, list[Record]] = {}
    for rec in records:
        acquisition_id = f"{rec['acquisition_date']}-{region}"
        grouped.setdefault(acquisition_id, []).append(rec)
    total = 0
    lidar_total = 0
    for acquisition_id, items in grouped.items():
        total += process_acquisition(acquisition_id, items, sensor_id, max_per_seq, output_dir)
        if lidar_paths:
            acquisition_root = os.path.join(output_dir, acquisition_id)
            print(f"Copying LiDAR files for {acquisition_id}...")
            lidar_total += copy_lidar_assets(acquisition_root, acquisition_id, lidar_paths)
            print(f"LiDAR copy complete for {acquisition_id}.")
    return total, lidar_total, len(grouped)
