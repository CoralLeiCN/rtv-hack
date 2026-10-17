# CEDA clip upload plan

Status as of 2026-10-17T11:10:37.611597Z: all 54 uploads accepted by VSS. Storage checks confirmed all sizes, private access, prompt and metadata. 0/54 clips are confirmed fully indexed. A background monitor in `~/cronjob/ceda-soc250721` on the VM updates the live index every 60 seconds until completion or a reported error. The repository index is a timestamped snapshot.

The source video is preserved. These 54 clips cover the original 1 hour 47 minutes 20 seconds. Video and both audio streams were copied without re-encoding; packet totals match the original. Every clip starts with a video keyframe and is below 100,000,000 bytes.

- Visibility: private to the uploader; no additional users.
- Capture type: `general`.
- Tags: `underwater,seabed,rov,ceda,JC241`.
- Location: eastern Clarion-Clipperton Zone, from dataset metadata.
- Camera ID: omitted.
- Processing: the existing VSS pipeline; no redeployment.

Analysis prompt:

> Describe visible seabed habitats, sediment, rocks, organisms, vehicle tracks, furrows and other visible disturbances. Read legible on-screen annotations. Separate observations from possible explanations; do not infer mining causes or historical dates unless explicitly shown.

Full provenance, checksums, paths and ingestion status are recorded in [external-videos.json](external-videos.json). Time ranges below are reported by the FFmpeg segment muxer; cuts follow keyframes. MB uses 1,000,000 bytes.

| File | Size MB | Source start seconds | Source end seconds |
| --- | ---: | ---: | ---: |
| JC241_HDSCI_DIVE403_17_clip_001.mp4 | 54.44 | 0.000 | 120.040 |
| JC241_HDSCI_DIVE403_17_clip_002.mp4 | 57.10 | 120.040 | 245.800 |
| JC241_HDSCI_DIVE403_17_clip_003.mp4 | 50.09 | 245.800 | 365.800 |
| JC241_HDSCI_DIVE403_17_clip_004.mp4 | 49.95 | 365.800 | 485.800 |
| JC241_HDSCI_DIVE403_17_clip_005.mp4 | 49.40 | 485.800 | 605.800 |
| JC241_HDSCI_DIVE403_17_clip_006.mp4 | 49.18 | 605.800 | 725.800 |
| JC241_HDSCI_DIVE403_17_clip_007.mp4 | 54.48 | 725.800 | 845.800 |
| JC241_HDSCI_DIVE403_17_clip_008.mp4 | 53.14 | 845.800 | 965.800 |
| JC241_HDSCI_DIVE403_17_clip_009.mp4 | 57.67 | 965.800 | 1086.560 |
| JC241_HDSCI_DIVE403_17_clip_010.mp4 | 52.77 | 1086.560 | 1204.520 |
| JC241_HDSCI_DIVE403_17_clip_011.mp4 | 39.64 | 1204.520 | 1324.520 |
| JC241_HDSCI_DIVE403_17_clip_012.mp4 | 44.40 | 1324.520 | 1444.520 |
| JC241_HDSCI_DIVE403_17_clip_013.mp4 | 44.51 | 1444.520 | 1564.520 |
| JC241_HDSCI_DIVE403_17_clip_014.mp4 | 51.35 | 1564.520 | 1684.520 |
| JC241_HDSCI_DIVE403_17_clip_015.mp4 | 59.24 | 1684.520 | 1804.520 |
| JC241_HDSCI_DIVE403_17_clip_016.mp4 | 56.80 | 1804.520 | 1924.520 |
| JC241_HDSCI_DIVE403_17_clip_017.mp4 | 67.78 | 1924.520 | 2044.520 |
| JC241_HDSCI_DIVE403_17_clip_018.mp4 | 66.55 | 2044.520 | 2164.520 |
| JC241_HDSCI_DIVE403_17_clip_019.mp4 | 61.19 | 2164.520 | 2284.520 |
| JC241_HDSCI_DIVE403_17_clip_020.mp4 | 57.11 | 2284.520 | 2404.520 |
| JC241_HDSCI_DIVE403_17_clip_021.mp4 | 60.83 | 2404.520 | 2524.520 |
| JC241_HDSCI_DIVE403_17_clip_022.mp4 | 60.76 | 2524.520 | 2644.520 |
| JC241_HDSCI_DIVE403_17_clip_023.mp4 | 58.36 | 2644.520 | 2764.520 |
| JC241_HDSCI_DIVE403_17_clip_024.mp4 | 59.83 | 2764.520 | 2884.520 |
| JC241_HDSCI_DIVE403_17_clip_025.mp4 | 61.54 | 2884.520 | 3004.520 |
| JC241_HDSCI_DIVE403_17_clip_026.mp4 | 59.89 | 3004.520 | 3124.520 |
| JC241_HDSCI_DIVE403_17_clip_027.mp4 | 61.58 | 3124.520 | 3244.520 |
| JC241_HDSCI_DIVE403_17_clip_028.mp4 | 58.87 | 3244.520 | 3364.520 |
| JC241_HDSCI_DIVE403_17_clip_029.mp4 | 58.39 | 3364.520 | 3484.520 |
| JC241_HDSCI_DIVE403_17_clip_030.mp4 | 65.06 | 3484.520 | 3604.520 |
| JC241_HDSCI_DIVE403_17_clip_031.mp4 | 58.54 | 3604.520 | 3724.520 |
| JC241_HDSCI_DIVE403_17_clip_032.mp4 | 52.94 | 3724.520 | 3844.520 |
| JC241_HDSCI_DIVE403_17_clip_033.mp4 | 50.22 | 3844.520 | 3964.520 |
| JC241_HDSCI_DIVE403_17_clip_034.mp4 | 53.55 | 3964.520 | 4084.520 |
| JC241_HDSCI_DIVE403_17_clip_035.mp4 | 53.10 | 4084.520 | 4204.520 |
| JC241_HDSCI_DIVE403_17_clip_036.mp4 | 55.62 | 4204.520 | 4324.520 |
| JC241_HDSCI_DIVE403_17_clip_037.mp4 | 53.30 | 4324.520 | 4444.520 |
| JC241_HDSCI_DIVE403_17_clip_038.mp4 | 49.89 | 4444.520 | 4564.400 |
| JC241_HDSCI_DIVE403_17_clip_039.mp4 | 51.04 | 4564.400 | 4684.400 |
| JC241_HDSCI_DIVE403_17_clip_040.mp4 | 50.44 | 4684.400 | 4804.400 |
| JC241_HDSCI_DIVE403_17_clip_041.mp4 | 49.87 | 4804.400 | 4923.440 |
| JC241_HDSCI_DIVE403_17_clip_042.mp4 | 54.64 | 4923.440 | 5043.120 |
| JC241_HDSCI_DIVE403_17_clip_043.mp4 | 55.92 | 5043.120 | 5162.000 |
| JC241_HDSCI_DIVE403_17_clip_044.mp4 | 53.97 | 5162.000 | 5287.240 |
| JC241_HDSCI_DIVE403_17_clip_045.mp4 | 52.69 | 5287.240 | 5406.160 |
| JC241_HDSCI_DIVE403_17_clip_046.mp4 | 55.97 | 5406.160 | 5528.200 |
| JC241_HDSCI_DIVE403_17_clip_047.mp4 | 64.69 | 5528.200 | 5646.480 |
| JC241_HDSCI_DIVE403_17_clip_048.mp4 | 67.04 | 5646.480 | 5760.400 |
| JC241_HDSCI_DIVE403_17_clip_049.mp4 | 81.04 | 5760.400 | 5884.640 |
| JC241_HDSCI_DIVE403_17_clip_050.mp4 | 77.57 | 5884.640 | 6003.400 |
| JC241_HDSCI_DIVE403_17_clip_051.mp4 | 60.80 | 6003.400 | 6124.320 |
| JC241_HDSCI_DIVE403_17_clip_052.mp4 | 61.11 | 6124.320 | 6241.640 |
| JC241_HDSCI_DIVE403_17_clip_053.mp4 | 70.50 | 6241.640 | 6365.400 |
| JC241_HDSCI_DIVE403_17_clip_054.mp4 | 40.83 | 6365.400 | 6440.080 |
