# Hackathon submission

[Ranger Duck submission draft](SUBMISSION_DRAFT.md) contains copy-ready project
answers. The [demo script](DEMO_SCRIPT.md) is maintained separately. The user supplied the
[London submission form](https://tokensand.com/vastlondon/submit) as the destination.

Source: `Builders_Challenge_Slides.pdf`, especially PDF pages 23–26; sponsor
resources on pages 18–20, workshop access on page 27, and prizes on page 31.
The supplied PDF is not stored in this repository. Submission guidance is also
in the [build-day guide](hackathon/BUILD_DAY.md#6-demos).

## Requirements

- Ship one working real-time video agent by the end of the build day. It should
  understand footage and act on it: search video in plain language, answer what
  happened, spot events, or trigger an action when something matters.
- Effectively use **at least three sponsor tools**.
- Submit by **4:30 PM** and include every team member on the submission.
- Give a working demo, not just a slide deck: **2 minutes** in the first round;
  the **top five teams** give a **3-minute demo** to everyone at **6:00 PM**.

## Judging criteria

| Criterion | What judges assess |
| --- | --- |
| Idea | A compelling application of the provided video search and summarization stack. |
| Technical implementation | High-quality software that is easy to follow, reproduce, and evaluate; clear documentation of inputs, outputs, and evaluation steps. |
| Design | Thoughtful, intuitive project design and user experience. |
| Impact | Effective use of at least three sponsor tools. |
| Presentation | A clear two-minute demonstration; demos are preferred over slides. |

## Submission and schedule

The [build-day guide](hackathon/BUILD_DAY.md#6-demos) directs London participants
to [tokensand.com/vastlondon](https://tokensand.com/vastlondon), then **Submit your
project**. Slide 26 instead lists
[tokensand.com/vastnyc](https://tokensand.com/vastnyc). Use the user-supplied
[London submission form](https://tokensand.com/vastlondon/submit). The guide says
submissions start around 4:30 PM, whereas
the slides explicitly set a 4:30 PM deadline; plan to submit **by 4:30 PM**.

| Time, as printed in the slides | Activity |
| --- | --- |
| 9:30 AM | Keynote and opening remarks |
| 10:00 AM | Hacking begins |
| 12:30 PM | Lunch |
| 4:30 PM | Project submission deadline |
| 4:45 PM | Judging and two-minute demos in a designated area |
| 6:00 PM | Top five teams: three-minute finalist demos |
| 6:30 PM | Awards ceremony |

## Available resources and prizes

- **Cursor:** coding agent with free credits.
- **Weights & Biases Inference:** one API for general-purpose models on
  **CoreWeave**, with free credits; **NVIDIA** provides accelerated computing.
- **VAST:** data platform and agent services, with the NVIDIA VSS Blueprint,
  loaded video data, and prepared Cursor skills.
- Workshop access: join [Cosmos](https://community.vastdata.com/c/workshop), open
  the [workshop portal](https://workshop.thecosmoslabs.com/), select your assigned
  team (Team-1 through Team-50), and follow the Cursor Remote SSH setup.
- Prizes: **first place — NVIDIA DGX Spark; second place — Hugging Face
  Microduck; top five — a $100 Amazon gift card for each presenting team**.

The slides do not specify scoring weights, team-size limits, required submission
files, eligibility or prior-work rules, or exactly what counts as a distinct
sponsor tool. The listed schedule does not state a date or timezone. Sponsor
resources above are context, not a confirmed tool-counting policy.

## Repository requirements

Separately, [AGENTS.md](../AGENTS.md) requires building on the deployed VSS APIs
without rebuilding or redeploying the shared DataEngine ingest pipeline. Deliver
a web app, CLI, or script that can be demonstrated from the workshop VM. Keep
credentials and generated secrets outside Git.
