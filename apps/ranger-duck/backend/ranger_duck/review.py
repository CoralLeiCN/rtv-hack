"""Local, offline manifest tool. Input/output may contain private source identities."""
import argparse
import json
from pathlib import Path
import sys

from .evidence import Manifest, MOTIONS, SAFE_ID, normalize_segments


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare private review manifests; never prints source identities.")
    commands = parser.add_subparsers(dest="command", required=True)
    draft = commands.add_parser("draft", help="Create unreviewed entries from a private raw VSS search response")
    draft.add_argument("--input", type=Path, required=True)
    draft.add_argument("--output", type=Path, required=True)
    approve = commands.add_parser("approve", help="Mark one entry reviewed after watching its actual video")
    approve.add_argument("--manifest", type=Path, required=True)
    approve.add_argument("--index", type=int, required=True, help="Zero-based entry index")
    approve.add_argument("--evidence-id", required=True)
    approve.add_argument("--animal", required=True)
    approve.add_argument("--behavior", choices=list(MOTIONS), required=True)
    approve.add_argument("--source-label", required=True)
    approve.add_argument("--note", default="")
    approve.add_argument("--interaction-partner", choices=["cat", "deer"])
    approve.add_argument("--interaction-evidence", default="",
                         help="After viewing, describe the explicit same-species pair and directed behavior")
    approve.add_argument("--confirm-viewed", action="store_true", required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "draft":
            data = json.loads(args.input.read_text())
            if not isinstance(data, dict) or not isinstance(data.get("results"), list):
                raise ValueError
            entries = [s.review_draft() for s in normalize_segments(data["results"])]
            # Exclusive create prevents overwriting a completed review accidentally.
            with args.output.open("x") as handle:
                handle.write(json.dumps({"version": 1, "references": entries}, indent=2) + "\n")
            args.output.chmod(0o600)
            print(f"Prepared {len(entries)} unreviewed entries. No actions enabled.")
        elif args.command == "approve":
            data = json.loads(args.manifest.read_text())
            if not SAFE_ID.fullmatch(args.evidence_id) or not args.animal.strip() or args.index < 0:
                raise ValueError
            reference = data["references"][args.index]
            reference.update(reviewed=True, evidence_id=args.evidence_id, animal=args.animal.strip().lower(),
                             behavior=args.behavior, source_label=args.source_label, review_note=args.note)
            if args.interaction_partner:
                if args.interaction_partner != args.animal.strip().lower() or not args.interaction_evidence.strip():
                    raise ValueError
                reference.update(interaction_partner=args.interaction_partner,
                                 interaction_evidence=args.interaction_evidence.strip())
            checked = Manifest([reference])
            if len(checked.entries) != 1:
                raise ValueError
            all_checked = Manifest(data["references"])
            if all_checked.warning:
                raise ValueError
            args.manifest.write_text(json.dumps(data, indent=2) + "\n")
            args.manifest.chmod(0o600)
            print("One review recorded. Restart the backend to load it.")
        else:
            checked = Manifest.load(args.manifest)
            if checked.warning:
                raise ValueError
            print(f"Valid reviewed entries: {len(checked.entries)}")
    except (OSError, ValueError, KeyError, TypeError, IndexError):
        print("Manifest operation failed. Check the input format, index, IDs, and output permissions.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
