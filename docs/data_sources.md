# Data Sources

The following summarizes the repository’s **17 October 2026 snapshots**, recorded
in the [external video index](../data/external-videos.json). These are historical
observations; ongoing ingestion may have advanced on the workshop VM.

| Dataset | Content | Recorded ingestion status | Footage duration |
| --- | --- | --- | --- |
| **MammAlps** | Forest, alpine, and nighttime wildlife footage from Swiss National Park; stored descriptions include deer, marmots, grazing, and movement. | 156 fully indexed uploads, producing 565 searchable segments. | Approx. 41.5 min |
| **KABR** | Savanna and aerial wildlife footage from Mpala Research Centre; stored descriptions include giraffes and zebras. Uploads include 40 RGB and 17 thermal videos. | 57 fully indexed uploads, producing 316 searchable segments. | Approx. 25.7 min |
| **Meow-10k** | Feline videos, with audio, time-series arrays, and annotations retained alongside the source videos. | 6,735 MP4s downloaded and verified; 29 videos indexed, 200 uploaded awaiting indexing, and 6,506 not yet submitted. | Indexed duration not recorded |
| **CEDA JC241 / DIVE403_17** | ROV footage from the eastern Clarion-Clipperton Zone; the analysis prompt covers seabed habitats, organisms, and visible disturbances. | 54 derived clips uploaded; none confirmed fully indexed in this snapshot. | Uploaded clips cover 1 h 47 min 20 s |

MammAlps and KABR were verified through the live VSS retrieval API and recorded
at 13:01 UTC. Their counts include pilot and quality-test uploads and do not
establish distinct original recordings or complete source-dataset coverage.
Animal descriptions above summarize stored AI captions. Source URLs, licences,
and citations for these two collections remain unverified in the index.

Meow-10k’s ingestion snapshot is from 11:32 UTC; its 16,870 verified downloaded
files include non-video companions that are not VSS video uploads. CEDA’s
snapshot is from 11:10 UTC; the original recording is preserved, with its 54
derived clips submitted separately. All uploads listed above use private
visibility. Uploaded or downloaded files are not counted as searchable until
indexing is confirmed.

See the [data guide](../data/README.md) for provenance, verification details, and
VM progress-file locations, the [Meow ingestion settings](../data/meow-ingestion-v1.json)
for its analysis prompt and tags, and the [CEDA clip record](../data/ceda-clip-upload-plan.md)
for its upload settings and source time ranges. Dataset citations and available
source references are retained in the [external video index](../data/external-videos.json).
