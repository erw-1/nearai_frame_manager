I made a tool to organize frames and metadata to respect the pipeline input data structure, so that we can share our data in a clean way. The default bucket size is 2k but it can be changed / overwritten with an argument if you prefer 10k now.
Here is a sample the ouptut: [nearai frame manager test.zip](https://github.com/user-attachments/files/24815694/nearai.frame.manager.test.zip) (only kept two files per sequences for file size)
<details><summary>structure of the folder</summary>
    <pre>
    C:.
├───20250423-HSN
│   ├───01_images
│   │   ├───S001
│   │   │       20250423-HSN_S001_Gopro_000001.jpg
│   │   │       20250423-HSN_S001_Gopro_000002.jpg
│   │   │
│   │   └───S002
│   │           20250423-HSN_S002_Gopro_000001.jpg
│   │           20250423-HSN_S002_Gopro_000002.jpg
│   │
│   ├───02_poses
│   │       coordinate_systems.json
│   │       S001_trajectory.csv
│   │       S001_trajectory.geojson
│   │       S002_trajectory.csv
│   │       S002_trajectory.geojson
│   │
│   ├───03_calibration
│   │       intrinsics.json
│   │
│   └───04_annotations
│       ├───S001
│       │       20250423-HSN_S001_Gopro_000001.json
│       │       20250423-HSN_S001_Gopro_000002.json
│       │
│       └───S002
│               20250423-HSN_S002_Gopro_000001.json
│               20250423-HSN_S002_Gopro_000002.json
│
└───20251210-NeoCapture
    ├───01_images
    │   ├───S001
    │   │       20251210-NeoCapture_S001_Trimblemx50_000001.jpg
    │   │       20251210-NeoCapture_S001_Trimblemx50_000002.jpg
    │   │
    │   └───S002
    │           20251210-NeoCapture_S002_Trimblemx50_000001.jpg
    │           20251210-NeoCapture_S002_Trimblemx50_000002.jpg
    │
    ├───02_poses
    │       coordinate_systems.json
    │       S001_trajectory.csv
    │       S001_trajectory.geojson
    │       S002_trajectory.csv
    │       S002_trajectory.geojson
    │
    ├───03_calibration
    │       intrinsics.json
    │
    ├───04_annotations
    │   ├───S001
    │   │       20251210-NeoCapture_S001_Trimblemx50_000001.json
    │   │       20251210-NeoCapture_S001_Trimblemx50_000002.json
    │   │
    │   └───S002
    │           20251210-NeoCapture_S002_Trimblemx50_000001.json
    │           20251210-NeoCapture_S002_Trimblemx50_000002.json
    │
    └───06_point_clouds
            20251210-NeoCapture_VOITEUR.laz (didn't include the 7 Gb file)
    </pre>
</details>

My idea was to send the tool to Nyon, _SIDEC du Jura_ and NeoCapture since their raw aquisitions are supported, to standardize the structure that we all provide on the cloud, I made it simple to use with an exe for them.
Does that sound good if we send you the data in one archive per aquisition with that structure ?

More info : 
- Tool repo, feel free to edit it or suggest changes https://github.com/erw-1/nearai_frame_manager
- Unlisted video of the tool handling a folder with two aquisitions (HSN / SIDEC and NeoCapture), with voiceover for explainations https://youtu.be/OoLVfKS38wE
