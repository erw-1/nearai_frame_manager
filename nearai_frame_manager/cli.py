"""CLI entrypoint for the NearAI frame manager."""
from __future__ import annotations

import argparse
import os
import sys
from typing import Any

from .common import date_from_folder_name, normalize_token
from .constants import MAX_FILES_PER_SEQUENCE, OUT_PARENT
from .csv_utils import find_pose_csv_path, load_pose_csv
from .exif_utils import extract_camera_model, extract_exif_metadata
from .io_utils import (
    collect_image_entries,
    collect_lidar_paths,
    find_acquisition_folders,
    find_first_image_path,
    find_lidar_paths,
)
from .models import AcquisitionCandidate, AcquisitionPlan, PoseLookup
from .processing import build_records, process_records_by_acquisition


def gather_input_dir(cli_dir: str | None, allow_gui: bool = True) -> str:
    """Resolve the input directory via CLI arg, GUI picker, or stdin."""
    if cli_dir:
        if os.path.isdir(cli_dir):
            return os.path.abspath(cli_dir)
        raise FileNotFoundError(f"Input folder not found: {cli_dir}")
    selected = ""
    if allow_gui:
        tk_module = None
        filedialog_module = None
        try:
            import tkinter as tk_module
            from tkinter import filedialog as filedialog_module
        except ImportError:
            pass
        if tk_module and filedialog_module:
            try:
                root = tk_module.Tk()
                root.withdraw()
                selected = filedialog_module.askdirectory(title="Select the folder that contains the images")
                root.destroy()
            except tk_module.TclError:
                selected = ""
    if not selected:
        selected = input("Folder containing the images: ").strip()
    if not selected:
        raise ValueError("No folder selected. Stopping.")
    if not os.path.isdir(selected):
        raise FileNotFoundError(f"Input folder not found: {selected}")
    return os.path.abspath(selected)


def resolve_region(raw: str | None, prompt: str) -> str:
    """Return a normalized region string, prompting if needed."""
    return normalize_token(raw or input(prompt), "Region")


def resolve_sensor_id(
    raw: str | None,
    default_sensor: str | None,
    prompt_prefix: str = "",
    *,
    allow_prompt: bool = True,
) -> str:
    """Return a normalized sensor ID from CLI, metadata, or prompt."""
    if raw:
        sensor_raw = raw
    elif default_sensor:
        if allow_prompt:
            entered = input(
                f"{prompt_prefix}Sensor ID - Press enter to use the value found in metadata "
                f"[{default_sensor}] or type a custom one (CamFront, GoPro, ...): "
            ).strip()
            sensor_raw = entered or default_sensor
        else:
            sensor_raw = default_sensor
    else:
        if not allow_prompt:
            raise ValueError("Sensor ID missing and no default sensor found in metadata.")
        sensor_raw = input(f"{prompt_prefix}Sensor ID (e.g., CamFront, GoPro): ")
    return normalize_token(sensor_raw, "Sensor ID")


def parse_region_sensor(line: str, default_sensor: str | None) -> tuple[str, str]:
    """Parse a line into (region, sensor_id), using default_sensor if needed."""
    if "," in line:
        parts = [part.strip() for part in line.split(",", 1)]
    else:
        parts = line.split()
    if not parts or not parts[0]:
        raise ValueError("Expected: <Region> [SensorID] or <Region>,<SensorID>.")
    region = normalize_token(parts[0], "Region")
    if len(parts) >= 2 and parts[1]:
        sensor_id = normalize_token(parts[1], "Sensor ID")
        return region, sensor_id
    if not default_sensor:
        raise ValueError("Sensor ID missing and no default sensor found in metadata.")
    return region, normalize_token(default_sensor, "Sensor ID")


def collect_batch_region_sensor(plans: list[AcquisitionPlan]) -> list[tuple[str, str]]:
    """Collect region/sensor pairs for each acquisition plan in order."""
    total = len(plans)
    print("\nProvide info for each acquisition folder.")
    print("Format: <Region> <SensorID>  or  <Region>,<SensorID>")
    print("Only enter <Region> to use the default sensor (if detected).\n")
    print(f"{total} acquisition(s) found:\n")
    for idx, plan in enumerate(plans, start=1):
        default_note = plan["default_sensor"] or "none"
        print(f" {idx}. {plan['name']} (default sensor: {default_note})")
    entries: list[tuple[str, str]] = []
    while len(entries) < total:
        if not entries:
            print("")
        prompt = f"[{len(entries) + 1}/{total}] "
        line = input(prompt).strip()
        if not line:
            raise ValueError("Batch entry cancelled or incomplete.")
        try:
            entries.append(parse_region_sensor(line, plans[len(entries)]["default_sensor"]))
        except ValueError as exc:
            print(f"Invalid entry: {exc}")
            continue
    return entries


def load_pose_lookup(
    path: str | None,
    epoch: str,
    *,
    soft_fail: bool,
    label: str | None = None,
) -> PoseLookup:
    """Load pose CSV data or return an empty mapping."""
    if not path:
        return {}
    try:
        return load_pose_csv(os.path.abspath(path), epoch)
    except (OSError, ValueError) as exc:
        if soft_fail:
            if label:
                print(f"Failed to read pose CSV {label}: {exc}", file=sys.stderr)
            else:
                print(f"Failed to read pose CSV: {exc}", file=sys.stderr)
            return {}
        raise


def is_auto_value(value: str | None) -> bool:
    """Return True when CLI value requests auto-detection."""
    return bool(value) and value.strip().lower() == "auto"


def build_plans(candidates: list[AcquisitionCandidate]) -> list[AcquisitionPlan]:
    """Create acquisition plans from detected candidates."""
    plans: list[AcquisitionPlan] = []
    for candidate in candidates:
        folder = candidate["folder"]
        sample_image = candidate["sample_image"]
        name = candidate["name"]
        pose_csv_path = find_pose_csv_path(folder)
        lidar_paths = find_lidar_paths(folder)
        folder_date = date_from_folder_name(name)
        sample_date, _ = extract_exif_metadata(sample_image)
        default_sensor = extract_camera_model(sample_image)
        acquisition_date = folder_date or sample_date
        plans.append(
            {
                "folder": folder,
                "name": name,
                "acquisition_date": acquisition_date,
                "pose_csv_path": pose_csv_path,
                "lidar_paths": lidar_paths,
                "default_sensor": default_sensor,
            }
        )
    return plans


def run_multi_acquisition(
    plans: list[AcquisitionPlan],
    pose_epoch: str,
    max_per_seq: int,
    output_dir: str,
) -> int:
    """Run multi-folder acquisition processing."""
    try:
        batch_entries = collect_batch_region_sensor(plans)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1

    total = 0
    lidar_total = 0
    acquisition_total = 0

    for plan, (region, sensor_id) in zip(plans, batch_entries, strict=True):
        print(f"\nProcessing {plan['name']}...")
        print(f"Sensor set to '{sensor_id}'. Scanning for images and metadata...")
        print("Loading images and building records...")

        pose_lookup = load_pose_lookup(
            plan["pose_csv_path"],
            pose_epoch,
            soft_fail=True,
            label=plan["pose_csv_path"],
        )
        image_entries = collect_image_entries(plan["folder"])
        if not image_entries:
            print(f"No JPEG images found in {plan['folder']}.")
            continue
        records = build_records(image_entries, pose_lookup)
        if not records:
            print(f"No readable images found in {plan['folder']}.")
            continue
        copied, copied_lidar, acquisition_count = process_records_by_acquisition(
            records,
            region,
            sensor_id,
            max_per_seq,
            output_dir,
            plan["lidar_paths"],
        )
        total += copied
        lidar_total += copied_lidar
        acquisition_total += acquisition_count

    print(f"\nDone. {total} files copied into {acquisition_total} acquisition folder(s).")
    if lidar_total:
        print(f"Copied {lidar_total} LiDAR file(s).")
    return 0


def run_single_acquisition(
    input_dir: str,
    output_dir: str,
    args: argparse.Namespace,
) -> int:
    """Run single-folder acquisition processing."""
    try:
        region = resolve_region(args.region, "General identifier for the acquisition (Nyon, HSN, ...): ")
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1

    pose_csv_path = args.pose_csv
    if is_auto_value(pose_csv_path):
        pose_csv_path = find_pose_csv_path(input_dir)
    try:
        pose_lookup = load_pose_lookup(pose_csv_path, args.pose_epoch, soft_fail=False)
    except (OSError, ValueError) as exc:
        print(f"Failed to read pose CSV: {exc}", file=sys.stderr)
        return 1

    try:
        if is_auto_value(args.lidar_path):
            lidar_paths = find_lidar_paths(input_dir)
        else:
            lidar_paths = collect_lidar_paths(args.lidar_path)
    except (FileNotFoundError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 1

    sample_image = find_first_image_path(input_dir)
    default_sensor = extract_camera_model(sample_image) if sample_image else None
    sensor_arg = None if is_auto_value(args.sensor) else args.sensor
    try:
        sensor_id = resolve_sensor_id(sensor_arg, default_sensor, allow_prompt=not is_auto_value(args.sensor))
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(f"Sensor set to '{sensor_id}'. Scanning for images and metadata...")
    print("Loading images and building records...")

    image_entries = collect_image_entries(input_dir)
    if not image_entries:
        print("No JPEG images found.")
        return 0
    records = build_records(image_entries, pose_lookup)
    if not records:
        print("No readable images found.")
        return 0
    total, lidar_total, acquisition_count = process_records_by_acquisition(
        records,
        region,
        sensor_id,
        args.max_per_seq,
        output_dir,
        lidar_paths,
    )
    print(f"\nDone. {total} files copied into {acquisition_count} acquisition folder(s).")
    if lidar_paths:
        print(f"Copied {lidar_total} LiDAR file(s).")
    return 0


def main() -> int:
    """CLI entrypoint for the lite frame manager."""
    parser = argparse.ArgumentParser(description="NearAI frame manager (lite).")
    parser.add_argument("input_dir", nargs="?", help="Input folder.")
    parser.add_argument("--region", help="Acquisition region/owner tag.")
    parser.add_argument("--sensor", help="Sensor label ('auto' to use metadata).")
    parser.add_argument("--max-per-seq", type=int, default=MAX_FILES_PER_SEQUENCE)
    parser.add_argument("--output-dir", default=OUT_PARENT)
    parser.add_argument("--pose-csv", help="Pose CSV path ('auto' to search).")
    parser.add_argument("--pose-epoch", choices=("gps", "unix"), default="gps", help="Pose time epoch.")
    parser.add_argument("--lidar-path", help="LiDAR file or folder ('auto' to search).")
    parser.add_argument("--no-gui", action="store_true")
    args = parser.parse_args()
    if args.max_per_seq <= 0:
        print("max-per-seq must be greater than zero.", file=sys.stderr)
        return 1

    no_args = (
        args.input_dir is None
        and not args.pose_csv
        and not args.lidar_path
        and not args.region
        and not args.sensor
    )

    def finalize(status: int) -> int:
        if no_args:
            input("Press Enter to exit...")
        return status

    if no_args:
        print("NearAI Frame Manager (CLI).")
        print("Can directly run with arguments instead (see README or https://github.com/erw-1/nearai_frame_manager).")

    try:
        input_dir = gather_input_dir(args.input_dir, allow_gui=not args.no_gui)
    except (ValueError, FileNotFoundError) as exc:
        print(exc, file=sys.stderr)
        return finalize(1)

    output_dir = os.path.abspath(args.output_dir)
    try:
        common = os.path.commonpath([os.path.abspath(input_dir), output_dir])
    except ValueError:
        common = None
    if common and common == os.path.abspath(input_dir):
        print("output-dir must be outside the input folder to avoid re-ingesting outputs.", file=sys.stderr)
        return finalize(1)

    interactive_multi = (
        args.input_dir is None
        and not args.pose_csv
        and not args.lidar_path
        and not args.region
        and not args.sensor
    )

    if interactive_multi:
        candidates = find_acquisition_folders(input_dir)
        if not candidates:
            print("No JPEG images found.")
            return finalize(0)
        plans = build_plans(candidates)
        status = run_multi_acquisition(plans, args.pose_epoch, args.max_per_seq, output_dir)
        return finalize(status)

    return run_single_acquisition(input_dir, output_dir, args)
