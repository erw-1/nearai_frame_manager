"""Filesystem IO helpers."""
import csv
import os
import shutil
from typing import Any

from .common import ensure_dirs
from .constants import POSE_FIELDS
from .models import AcquisitionCandidate, ImageEntry


def collect_image_entries(folder: str) -> list[ImageEntry]:
    """Collect JPEG file entries with stat metadata."""
    entries: list[ImageEntry] = []
    for root, _dirs, files in os.walk(folder):
        for file in files:
            if not file.lower().endswith((".jpg", ".jpeg")):
                continue
            path = os.path.join(root, file)
            try:
                stat = os.stat(path)
            except OSError:
                continue
            entries.append({"path": path, "mtime": stat.st_mtime})
    return entries


def find_first_image_path(folder: str) -> str | None:
    """Return the first JPEG found under a folder."""
    for root, _dirs, files in os.walk(folder):
        for file in sorted(files):
            if file.lower().endswith((".jpg", ".jpeg")):
                return os.path.join(root, file)
    return None


def find_acquisition_folders(root: str) -> list[AcquisitionCandidate]:
    """Find acquisition folders based on presence of JPEG images."""
    try:
        entries = sorted(os.listdir(root))
    except OSError:
        return []
    candidates: list[AcquisitionCandidate] = []
    for entry in entries:
        path = os.path.join(root, entry)
        if not os.path.isdir(path):
            continue
        sample_image = find_first_image_path(path)
        if sample_image:
            candidates.append({"folder": path, "name": entry, "sample_image": sample_image})
    if candidates:
        return candidates
    sample_image = find_first_image_path(root)
    if sample_image:
        return [
            {
                "folder": root,
                "name": os.path.basename(os.path.normpath(root)),
                "sample_image": sample_image,
            }
        ]
    return []


def scan_lidar_files(folder: str) -> list[str]:
    """Return sorted LiDAR file paths under a folder."""
    lidar_files: list[str] = []
    for root, _dirs, files in os.walk(folder):
        for file in files:
            if file.lower().endswith((".laz", ".las")):
                lidar_files.append(os.path.abspath(os.path.join(root, file)))
    lidar_files.sort()
    return lidar_files


def find_lidar_paths(folder: str) -> list[str]:
    """Auto-detect LiDAR files under a folder."""
    return scan_lidar_files(folder)


def collect_lidar_paths(lidar_path: str | None) -> list[str]:
    """Resolve LiDAR paths from a file or directory argument."""
    if not lidar_path:
        return []
    if os.path.isdir(lidar_path):
        files = scan_lidar_files(lidar_path)
        if not files:
            raise ValueError(f"No LiDAR files (.laz/.las) found in {lidar_path}.")
        return files
    if os.path.isfile(lidar_path):
        return [os.path.abspath(lidar_path)]
    raise FileNotFoundError(f"LiDAR path not found: {lidar_path}")


def copy_lidar_assets(acquisition_root: str, acquisition_id: str, lidar_paths: list[str]) -> int:
    """Copy LiDAR files into the acquisition output folder."""
    if not lidar_paths:
        return 0
    lidar_root = os.path.join(acquisition_root, "06_point_clouds")
    ensure_dirs(lidar_root)
    copied = 0
    acquisition_prefix = f"{acquisition_id}_".lower()
    for lidar_path in lidar_paths:
        base_name = os.path.basename(lidar_path)
        dest_name = base_name if base_name.lower().startswith(acquisition_prefix) else f"{acquisition_id}_{base_name}"
        dest_path = os.path.join(lidar_root, dest_name)
        if os.path.abspath(lidar_path) == os.path.abspath(dest_path):
            continue
        shutil.copy2(lidar_path, dest_path)
        copied += 1
    return copied


def write_trajectory_csv(path: str, rows: list[dict[str, Any]]) -> None:
    """Write a trajectory CSV to disk."""
    ensure_dirs(os.path.dirname(path))
    with open(path, "w", newline="", encoding="utf-8") as csv_fp:
        writer = csv.DictWriter(csv_fp, fieldnames=POSE_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in POSE_FIELDS})


def write_json(path: str, payload: dict[str, Any]) -> None:
    """Write JSON payload with UTF-8 encoding and pretty formatting."""
    import json

    ensure_dirs(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
