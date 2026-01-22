"""NearAI frame manager.

Assumptions:
- Input is raw data only (no previously generated outputs).
- Image filenames are unique across the input tree.
- LiDAR files live in the same folder/subfolders as their images.
"""
from nearai_frame_manager.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
