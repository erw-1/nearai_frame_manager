# NearAI Frame Manager

CLI entrypoint `run.py` or `python -m nearai_frame_manager`  
Organizes raw 360° image collections
into the NearAI acquisition layout, extracts EXIF metadata, optionally merges
pose CSV data, and copies LiDAR files.

## Assumptions

- Input is unprocessed data only (jpg, csv, las/laz).
- Image filenames are unique across the input tree.
- LiDAR files belong to the same folder/subfolders as their images.

## Outputs

```
<output_dir>/
  <AcquisitionID>/
    01_images/
      S001/
        <AcquisitionID>_S001_<SensorID>_000001.jpg
        ...
    02_poses/
      S001_trajectory.csv
      coordinate_systems.json
    03_calibration/
      intrinsics.json
    04_annotations/
      S001/
        <AcquisitionID>_S001_<SensorID>_000001.json
        ...
    06_point_clouds/  (optional)
      <AcquisitionID>_<lidar_file>.las/.laz
```

## Naming

`<AcquisitionID>_<SequenceID>_<SensorID>_<FrameIndex>.<ext>`

- AcquisitionID: `YYYYMMDD-Region` (Region = organization / campaign id)
- SequenceID: `S###`
- SensorID: e.g., `CamFront`, `GoProMax`
- FrameIndex: 6-digit zero-padded, resets per sequence

## Requirements

- Python 3.10+
```
pip install piexif
```

## Flow Overview

1. Scan input folders and detect acquisitions + optional pose CSV/LiDAR.
2. Build per-image records (EXIF + CSV overrides + acquisition date).
3. Write images, annotations, poses, and calibration outputs.

## Command Examples

### 1) Interactive multi-folder mode (raw data root with several aquisition folders): auto sensor, pose csv and lidar detection per folder
```
python run.py
```

### 2) Single acquisition folder with output + CSV + LiDAR
```
python run.py "./test_data/neocapture/voiteur" --region NeoCapture --sensor auto --pose-csv auto --lidar-path auto --output-dir "./out"
```

### 3) Single acquisition with custom sequence size
```
python run.py "./test_data/hsn/20250423_C02" --region HSN --sensor auto --max-per-seq 10000
```

## Arguments

- `input_dir`           Input folder (if omitted, a picker/prompt is used).
- `--region`            Acquisition region/owner/org tag.
- `--sensor`            Sensor label (e.g., GoProMax). `auto` uses metadata.
- `--output-dir`        Output root (default: repo root or exe folder).
- `--pose-csv`          Pose CSV path: `auto` will look for a .csv.
- `--lidar-path`        LiDAR file path: `auto` will look for .las or .laz.
- `--pose-epoch`        Pose time epoch: `gps`(default) or `unix`.
- `--max-per-seq`       Sequence size (default 2000).
- `--no-gui`            Disable the folder picker.

## Build EXE for your less technical colleagues

```
pip install piexif pyinstaller
pyinstaller --onefile --name nearai_frame_manager --console run.py
```
Or download it from GitHub Releases.
