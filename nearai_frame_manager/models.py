"""Typed structures used across the frame manager."""
from typing import Any, TypedDict


class PoseRow(TypedDict, total=False):
    file_name: str
    gps_seconds: float
    timestamp: str
    gps_latitude: float
    gps_longitude: float
    gps_altitude_m: float
    heading_deg: float
    pitch_deg: float
    roll_deg: float


class ImageEntry(TypedDict):
    path: str
    mtime: float


class Record(TypedDict):
    src: str
    ext: str
    original_name: str
    acquisition_date: str
    derived: dict[str, Any]
    mtime: float
    csv_pose: PoseRow | None


class AcquisitionPlan(TypedDict):
    folder: str
    name: str
    acquisition_date: str | None
    pose_csv_path: str | None
    lidar_paths: list[str]
    default_sensor: str | None


PoseLookup = dict[str, PoseRow]


class AcquisitionCandidate(TypedDict):
    folder: str
    name: str
    sample_image: str
