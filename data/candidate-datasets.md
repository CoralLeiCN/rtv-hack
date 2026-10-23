# Candidate video datasets

Candidate sources identified during research on 17 October 2026, documented on
23 October 2026. The initial search covered UK and London footage; the later
priority was interesting footage with a useful conservation or accessibility
application. Geography outside the UK is marked explicitly.

Counts and access details below are research snapshots from the linked dataset
cards and file listings, not a fresh download audit. This catalog is not a local
media or ingestion inventory. See [the data guide](README.md) and
[existing provenance records](external-videos.json) for recorded imports.

## Shortlist for conservation and accessibility

### SMARTEX / JC241 deep-sea habitat survey

- **Location:** eastern Clarion-Clipperton Zone, Pacific Ocean. UK-led expedition;
  this is not footage from UK waters.
- **Footage:** ISIS remotely operated vehicle recordings at approximately
  4,700 metres depth, collected in 2023. The survey includes a seabed site
  disturbed by a mining machine in 1979.
- **Access:** [dataset record](https://catalogue.ceda.ac.uk/uuid/c701076b44c14a918f7cdb9641bf2d78/)
  and [download directory](https://data.ceda.ac.uk/bodc/deposits01/soc250721).
  The listing contains 12 MP4 videos plus three supporting files, approximately
  45 GB in total. Public access is available without registration.
- **Example:** [JC241_HDSCI_DIVE403_17.mp4](https://dap.ceda.ac.uk/bodc/deposits01/soc250721/JC241_HDSCI_DIVE403_17.mp4?download=1).
  Existing provenance records its size as 3,057,037,896 bytes, approximately
  3.06 GB or 2.85 GiB.
- **Rights:** Open Government Licence v3; cite the dataset authors and DOI
  [10.5285/2de087c9-cee3-87f4-e063-7086abc0f9a9](https://doi.org/10.5285/2de087c9-cee3-87f4-e063-7086abc0f9a9).
- **Possible application:** retrieve visible organisms and disturbance traces,
  then assemble timestamped evidence for marine researchers. A generated caption
  alone cannot establish species identity, population change or ecological recovery.

This is the strongest match to the ocean-conservation idea discussed in the
research. The catalog description applies to the collection; inspect each clip
before claiming it depicts a particular organism or disturbance.

### Prompting-MammAlps / MammAlps-S2

- **Location:** Swiss National Park, Switzerland; not UK footage.
- **Footage:** 2,865 camera-trap MP4 clips, 18.4 hours, seven mammal species,
  approximately 75 GB uncompressed. Includes animal tracks and behaviour labels.
- **Access:** [Hugging Face dataset and file instructions](https://huggingface.co/datasets/amathislab/Prompting-MammAlps).
- **Evaluation:** 135 natural-language queries are linked to matching videos,
  providing a way to measure retrieval quality instead of judging only a demo.
- **Rights:** CC BY-NC 4.0; non-commercial use.
- **Possible application:** help ecologists find feeding, nursing, chasing and
  other interactions, with source clips and a reviewable observation log.

Do not assume this release is the same source or revision as the historical
MammAlps imports in this repository. Their unresolved provenance fields must
remain unresolved until matched to the original source.

### VIP-Mobility360

- **Location:** United Kingdom.
- **Footage:** outdoor mobility obstacles relevant to people with visual
  impairments, including bollards, bins, construction barriers and pavement
  cracks. The publisher reports 100 sequences per object class.
- **Access:** [Liverpool John Moores University dataset](https://opendata.ljmu.ac.uk/id/eprint/226/),
  with a 110 GB full archive and supporting documentation.
- **Rights:** the repository lists Creative Commons Attribution; confirm the
  exact licence version and annotation coverage in the downloaded documentation.
- **Possible application:** identify candidate access barriers and generate
  timestamped evidence for human-reviewed accessibility audits. Archive footage
  does not establish the current safety or accessibility of a route.

### UKCEH FluViSat river and tidal footage

- **Location:** UK subset includes River Tweed at Norham, England, and Falls of
  Lora at Connel, Scotland. The full collection also includes Australia,
  Switzerland and Japan.
- **Footage:** stationary overhead drone MP4s, at least 20 seconds and 1080p.
  UK recordings include SRT flight metadata with position and altitude.
- **Access:** [UKCEH dataset and files](https://catalogue.ceh.ac.uk/documents/d62347ba-0173-4857-b3fc-b7238988f0d8).
  The entire multinational collection is approximately 11.9 GB.
- **Rights:** Open Government Licence; retain the dataset citation.
- **Possible application:** retrieve comparable river observations and support
  surface-flow research. Quantitative flow estimates require calibrated analysis;
  this is not a labelled pollution or flood-prediction dataset.

A smaller UK alternative is the [River Sheaf flow-video dataset](https://catalogue.ceh.ac.uk/documents/478db67e-bd58-48d9-a540-9e8e7e3ae68a):
five three-minute MP4s from one Sheffield river reach, recorded in August 2024,
with 2.7K/4K and 30/60 fps variants, under the Open Government Licence. It is
suitable for a small reproducible flow-analysis demonstration, with less visual
variety than the other candidates.

## Other UK and London candidates

These remain useful sources, although road traffic was subsequently deprioritised.

| Candidate | Geography and scale | What is actually available | Limitations and rights |
| --- | --- | --- | --- |
| [Oxford Day and Night](https://huggingface.co/datasets/active-vision-lab/oxford-day-and-night) | 124 first-person recordings at five Oxford locations, indoors/outdoors and day/dusk/night | Face-blurred MP4s; camera folder `214-1` is RGB. Other folders contain sensor and 3D assets. | CC BY 4.0. Download selected MP4s rather than the entire multimodal repository. |
| [UK-Road-DashCam](https://huggingface.co/datasets/aap9002/UK-Road-DashCam/tree/main) | Described as UK footage; 274 video entries and about 175 GB | Actual MP4 files hosted on Hugging Face | Sparse documentation; exact routes and London coverage unconfirmed. The repository is tagged MIT, but provenance and the scope of footage permissions need checking. |
| [ROAD](https://github.com/gurkirt/road-dataset#download) | Oxford driving; 22 videos, 170 minutes total | MP4 downloads via the official project, with road-user/action annotations | Outside Hugging Face. Academic use only according to the project terms. [Paper](https://arxiv.org/abs/2102.11585). |
| [360DVO](https://huggingface.co/datasets/chris1004336379/360DVO) | Global collection including a sequence named `london bridge` | Panoramic image sequences, standardised to 3840 x 1920 at 10 fps | Frames, not ready MP4s. Confirm sequence provenance and reuse terms before converting or importing. |
| [Sekai](https://huggingface.co/datasets/Lixsp11/Sekai) | Global walking/drone footage; metadata includes Borough Market, London | Real-world annotations and camera data on Hugging Face; source video requires separate YouTube downloads using the [official tools](https://github.com/Lixsp11/sekai-codebase) | About 299,000 walking clips is the worldwide count, not the UK count. The UK subset has not been counted. Game footage is a separate subset. Review the project licence and source-video permissions. |
| [Mixkit-Src](https://huggingface.co/datasets/FastVideo/Mixkit-Src/tree/main/Traffic) | Mixed countries, with a London buildings clip identified by filename | Actual short MP4 files on Hugging Face | Not a dedicated UK collection; UK count unknown. Check the original Mixkit clip licence rather than assuming the mirror grants reuse rights. |
| [WebVid-10M mirror](https://huggingface.co/datasets/TempoFunk/webvid-10M) | Global stock-footage descriptions, including London/UK entries | CSV metadata: `videoid`, `contentUrl`, `duration`, `page_dir`, `name`; videos are external links | `name` is a free-text caption, not a fixed class label. No structured location field or bounding boxes in this schema. UK count and working video-link count unknown. Mirror metadata licensing does not establish footage rights. |

The [original WebVid project](https://github.com/m-bain/webvid) states that it
stopped distributing URLs and captions following a Shutterstock request. Treat
the Hugging Face copy as a third-party metadata mirror, not an assured source of
available or reusable video.

## Additional wildlife source and weaker leads

- **[MammalNet](https://huggingface.co/datasets/linxxx3/MammalNet):** a third-party
  Hugging Face mirror lists MP4s in a compressed archive. The
  [original project](https://github.com/Vision-CAIR/MammalNet) describes more than
  18,000 videos and 539 hours across 173 mammal categories and 12 high-level
  behaviours. These are original-dataset totals, not a verified mirror count.
  UK-only coverage was not established; verify mirror completeness and original
  access terms before using it.
- **[Oxford RobotCar place-recognition subset](https://huggingface.co/datasets/OPR-Project/OxfordRobotCar_OpenPlaceRecognition):**
  Oxford driving imagery, approximately 21.7 GB, tagged CC BY-NC-SA 4.0. It is
  preprocessed imagery/sensor data, not a ready MP4 collection.
- **[Walking Tours](https://huggingface.co/datasets/shawshankvkt/Walking_Tours):**
  the published city list contains no UK location. It provides YouTube links and
  download tools; it was not retained as a UK candidate.
- **[EPIC-KITCHENS-100 mirror](https://huggingface.co/datasets/awsaf49/epic_kitchens_100):**
  potentially useful for everyday activity understanding, but a UK-only
  participant partition was not verified. Do not label the full collection UK.

## Existing downloads versus candidate sources

[external-videos.json](external-videos.json) already contains historical records
of CEDA downloads on the workshop VM, Meow-10k downloads, and MammAlps/KABR
imports. Those records do not establish present file availability or current
indexing state. They also do not mean every dataset in this catalog was acquired.

A check of an old repository worktree found no playable media there. That result
does not describe other worktrees, the workshop VM, an external media directory,
or the current archive. Keep these quantities separate when reporting inventory:
source recordings, downloaded files, derived clips, parent uploads and indexed
segments. Use the [archive operations guide](../docs/guides/archive.md) to verify
the selected environment before reporting current availability.
