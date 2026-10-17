Downloaded public assets are intentionally excluded from Git. Before starting
or building the frontend, run from the repository root:

```sh
python3 apps/ranger-duck/scripts/simulator-assets.py
```

The script resolves the pinned official Microduck revision and checks every
file against its recorded SHA-256 digest. Use `--check` for an offline check.
Source and attribution are in `../../src/simulator/upstream/`.
