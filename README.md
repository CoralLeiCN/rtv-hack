# VAST Builders Challenge: Video Agents

Build video agents on the deployed VSS stack using its search, metadata,
detections, and video APIs.

[Ranger Duck](apps/ranger-duck/README.md) combines a simulated wildlife encounter,
archive search, video evidence, and the existing Microduck movement policies in
one demo page.

Hackathon documentation lives in [`docs/hackathon/`](docs/hackathon/):

- [Build day guide](docs/hackathon/BUILD_DAY.md)
- [Submission requirements, judging criteria, and schedule](docs/SUBMISSION.md)
- [Before you build](docs/hackathon/BEFORE_YOU_BUILD.md)
- [Architecture reference](docs/hackathon/ARCHITECTURE_REFERENCE.md)
- [Infrastructure onboarding (PDF)](docs/hackathon/BUILDERS-CHALLENGE-INFRA-ONBOARDING.pdf)

For agent setup and workflows, see the [Codex setup and skill catalog](docs/CODEX.md),
[repository instructions](AGENTS.md), [Codex skills](.agents/skills/), and
[Cursor skills](.cursor/README.md). [`config.example`](config.example) documents
the environment variables used by the skills.

To connect from your laptop, follow the [service connection guide](docs/SERVICE_CONNECTIONS.md).
External video sources, licences, verification and ingestion status are tracked in
the [external video index](data/README.md). Dataset download and ingestion scripts
are in [`cronjob/ceda-soc250721`](cronjob/ceda-soc250721/README.md).
