# Connect to the workshop services from Codex

Run Codex on your laptop and use SSH to execute service calls on the workshop
VM. The VM already has the network access and team configuration needed for the
services. This workflow does not require installing Codex on the VM, copying
credentials to the laptop, or redeploying the stack.

```text
Codex on your laptop
  -> SSH host alias, using cloudflared
  -> Workshop VM
  -> VSS API, GPU models, VastDB, and S3
```

The SSH connection, VSS login, identity check, and archive-count query in this
workflow were verified on 17 October 2026. The service map below also describes
the other connections available through the repository skills.

## Install cloudflared on macOS

Skip installation if `$HOME/bin/cloudflared` already exists. These commands use
the matching official binary for Apple silicon or Intel Macs and keep an
existing binary. Run them in a terminal on your laptop:

```bash
bash <<'LOCAL'
set -euo pipefail
uname -s
uname -m
if [ "$(uname -s)" != Darwin ]; then
  echo 'These installation commands are for macOS.' >&2
  exit 1
fi
if [ ! -e "$HOME/bin/cloudflared" ]; then
  case "$(uname -m)" in
    arm64) lab_arch=arm64 ;;
    x86_64) lab_arch=amd64 ;;
    *) echo 'Unsupported Mac architecture.' >&2; exit 1 ;;
  esac
  lab_tmp=$(mktemp -d)
  trap 'rm -rf "$lab_tmp"' EXIT
  curl --fail --location --show-error --silent \
    "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-${lab_arch}.tgz" \
    --output "$lab_tmp/cloudflared.tgz"
  tar -xzf "$lab_tmp/cloudflared.tgz" -C "$lab_tmp" cloudflared
  mkdir -p "$HOME/bin"
  install -m 755 "$lab_tmp/cloudflared" "$HOME/bin/cloudflared"
  xattr -d com.apple.quarantine "$HOME/bin/cloudflared" || true
fi
"$HOME/bin/cloudflared" --version
LOCAL
```

An xattr message saying the quarantine attribute does not exist is harmless.
If macOS still blocks the binary, use **System Settings > Privacy & Security >
Open Anyway**. No Homebrew or other package manager is needed.

## Configure and connect through SSH

Use the alias, hostname, and username from your lab portal. The following values
are placeholders. Keep real connection details in your local `~/.ssh/config`.
Create `~/.ssh` and the config file if needed; replace an existing block for the
same alias instead of adding a duplicate. Preserve unrelated entries.

```sshconfig
Host bc-YOUR_USERNAME
  HostName YOUR_LAB_HOSTNAME
  User YOUR_USERNAME
  IdentityFile ~/.ssh/id_ed25519_cursor
  # If your registered key has a different filename, add it explicitly:
  # IdentityFile ~/.ssh/YOUR_EXISTING_PRIVATE_KEY
  ProxyCommand "$HOME/bin/cloudflared" access ssh --hostname %h
```

Keep the `id_ed25519_cursor` line even when using Codex. It is a filename, not a
requirement to use Cursor. If your portal-registered key has a different name,
uncomment the second `IdentityFile` line and replace its filename with that
existing private key. The private key stays on the laptop; its matching public
key must already be registered through the lab portal.

Do not set `IdentitiesOnly`. A missing identity file produces a warning and SSH
can continue with other configured identities and keys available in the agent.
SSH does not scan every private-key file in `~/.ssh`, so name your chosen file
explicitly. Do not store a VM password in the SSH config.

On the laptop, replace the alias below once, then connect:

```bash
LAB_SSH_ALIAS='bc-YOUR_USERNAME'
ssh "$LAB_SSH_ALIAS"
```

Always use the alias from the `Host` line. Connecting to the real hostname
directly skips this block. Do not add a username to this command; the `User`
line supplies it.

If Cloudflare opens a browser login, complete it yourself. An existing session
may let SSH proceed without showing a browser. On a first connection, SSH may
also ask you to confirm the VM's host key. A remote shell prompt confirms that
SSH succeeded. If it asks for a VM password instead, check the selected key and
its portal registration.

## Use the connection from Codex

Keep this repository open in Codex on the laptop so it can read `AGENTS.md` and
the skills. Tell Codex which SSH alias to use and ask for an operation:

```text
Use my configured SSH alias to run $retrieval-dashboard on the VM.
Use $retrieval-search through that SSH connection to find people near an entrance.
Use $retrieval-agent-qa to answer a question about the archive with video evidence.
```

Local repository edits stay on the laptop. Commands explicitly sent through
SSH execute on the VM. The query example below sends a script through SSH
without saving a script or installing software on the VM.

Codex's native remote-project mode is a separate setup: it requires Codex
installed and authenticated on the VM, followed by **Settings > Connections**
in the app. That installation is unnecessary for this laptop-and-SSH workflow.
See the [official remote connection guide](https://learn.chatgpt.com/docs/remote-connections#connect-to-an-ssh-host)
if you later choose that mode.

## Keep service configuration on the VM

SSH and Cloudflare get you onto the VM. Each service then uses its own
authentication, summarized below. Use existing environment variables or the
single absolute `/config/*.config` team file. `config.example` documents names
only; do not fill it with real credentials or source its placeholders.

Use Bash on the VM. Examples using `mapfile` require Bash 4 or newer, and macOS
zsh reserves `USERNAME`. Keep configuration loading, login, and service calls
in the same remote shell session.

To inspect available variable names without revealing their values, run this
inside the VM:

```bash
env | cut -d= -f1 | sort
```

If configuration is missing or more than one team file exists, resolve the
configured environment before continuing. Do not guess endpoints, search the
repository's `team-configs/`, copy secrets into Git, or paste secrets into chat.

## Run a read-only archive query

Run this from the laptop after setting `LAB_SSH_ALIAS` as above. It loads the
VM configuration when needed, logs in to the VSS API, checks `auth/me`, and
returns counts for all videos visible to your account. Passwords and the JWT
stay in the remote process; only counts and sanitized errors are printed.

```bash
ssh -o BatchMode=yes -o ConnectTimeout=20 "$LAB_SSH_ALIAS" 'bash -s' <<'REMOTE'
set -eo pipefail
set +x
if [ -z "${INGRESS_URL:-}" ] || [ -z "${USERNAME:-}" ] || [ -z "${PASSWORD:-}" ]; then
  mapfile -t LAB_CONFIG_FILES < <(find /config -maxdepth 1 -type f -name '*.config' | sort)
  if (( ${#LAB_CONFIG_FILES[@]} != 1 )); then
    echo 'Expected exactly one /config/*.config file.' >&2
    exit 1
  fi
  set -a
  source "${LAB_CONFIG_FILES[0]}" >/dev/null 2>&1 || {
    echo 'Unable to load the team configuration.' >&2
    exit 1
  }
  set +a
fi
python3 - <<'PY'
import json
import os
import sys
import urllib.error
import urllib.request

missing = [name for name in ("INGRESS_URL", "USERNAME", "PASSWORD")
           if not os.environ.get(name)]
if missing:
    sys.exit("Missing configuration variables: " + ", ".join(missing))

base = os.environ["INGRESS_URL"].rstrip("/")
token = None

def request(path, data=None, timeout=30):
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    body = None
    if data is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(data).encode()
    try:
        req = urllib.request.Request(base + path, data=body, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        sys.exit(f"API request {path} returned HTTP {exc.code}.")
    except Exception as exc:
        sys.exit(f"API request {path} failed ({type(exc).__name__}).")

login = request("/api/v1/auth/login", {
    "username": os.environ["USERNAME"],
    "password": os.environ["PASSWORD"],
})
token = login.get("access_token")
if not token:
    sys.exit("Login did not return an access token.")
request("/api/v1/auth/me")
stats = request("/api/v1/dashboard/stats?scope=all", timeout=90)
overview = stats.get("overview", {})
alignment = stats.get("pipeline_alignment", {})
print(json.dumps({
    "unique_videos": overview.get("unique_videos"),
    "fully_indexed_videos": overview.get("fully_indexed_videos"),
    "indexed_clips": overview.get("indexed_clips"),
    "duplicate_segment_rows": overview.get("duplicate_segment_rows"),
    "pending_index": alignment.get("pending_index"),
}, indent=2))
PY
REMOTE
```

`scope=all` still respects the account's visibility permissions. Use
`scope=mine` for the caller's uploads. The token is held only in the remote
process and is not saved; running the command again logs in again. Its expiry
is controlled by the backend. A `null` count means the response did not provide
that field, rather than a count of zero.

For search, use [`retrieval-search`](../.agents/skills/retrieval-search/SKILL.md)
with `POST /api/v1/search`. For an answer backed by video evidence, use
[`retrieval-agent-qa`](../.agents/skills/retrieval-agent-qa/SKILL.md) with
`POST /api/v1/agent/ask`. Resolve time, location, camera, and other metadata
filters with [`retrieval-list-metadata`](../.agents/skills/retrieval-list-metadata/SKILL.md).

## Service access map

Run these service calls on the VM. Obtain actual endpoints and credentials from
its configuration; the names below are not literal endpoint addresses.

| Service | Configuration | Authentication and access |
| --- | --- | --- |
| VSS retrieval API | `INGRESS_URL`, `USERNAME`, `PASSWORD` | Login at `/api/v1/auth/login`; send the returned JWT as a bearer token. Start with [`retrieval-login`](../.agents/skills/retrieval-login/SKILL.md). |
| GPU models | `COSMOS3_REASON_URL`, `YOLO_URL`, `COSMOS_EMBED1_URL`, `CANARY_1B_URL`, `GPU_BEARER_TOKEN` | Send the separate GPU bearer token. Use [`gpu-models`](../.agents/skills/gpu-models/SKILL.md) and [`gpu-model-health`](../.agents/skills/gpu-model-health/SKILL.md). |
| VastDB | `S3_ENDPOINT`, `ACCESS_KEY`, `SECRET_KEY`, `VASTDB_BUCKET`, `VDB_SCHEMA`, `VDB_COLLECTION` | Use the Python SDK with the access/secret key pair. The default endpoint is the data VIP from `S3_ENDPOINT`. Follow [`vast-database-vastdb-read`](../.agents/skills/vast-database-vastdb-read/SKILL.md). |
| S3 video assets | `S3_ENDPOINT`, `ACCESS_KEY`, `SECRET_KEY`, `S3_CHUNKS_BUCKET`, `S3_SEGMENTS_BUCKET` | Use the team's configured buckets. Prefer [`retrieval-videos`](../.agents/skills/retrieval-videos/SKILL.md) for user-facing playback and metadata. |
| Kubernetes diagnostics | `KUBECONFIG`, `/config/kubeconfig` or its team-prefixed equivalent | Use [`deploy-health`](../.agents/skills/deploy-health/SKILL.md) for deployment diagnostics. Ordinary queries need no deployment changes. |

Direct VastDB access is limited by the team's identity policy and does not apply
the retrieval API's user-level visibility filters. Stay in `VASTDB_BUCKET` and
exclude `vectors` and `vectors_visual` from ordinary row inspection. Use the
configured Query Engine endpoint only when that read path is specifically
needed; writes use the data VIP.

GPU health paths differ by model:

| Model | Supported health paths |
| --- | --- |
| Cosmos3-Reason and Embed1 | `/v1/models`, `/v1/health/ready`, `/v1/health/live` |
| YOLO11 | `/healthz`; check `ok` and `model_loaded` |
| Canary-1B | `/v1/health/ready`, `/v1/health/live` |

Use the configured URL for each model rather than deriving one endpoint from
another. A 404 from `/v1/models` on YOLO or Canary does not establish a service
failure. Canary is optional speech recognition, outside the default ingest
pipeline.

## Troubleshoot a connection

| Symptom | Next step |
| --- | --- |
| Missing `id_ed25519_cursor` warning | Keep that required line and add the actual portal-registered key as another `IdentityFile`. |
| SSH asks for a VM password or rejects the public key | Check the local key path and portal registration. Do not put a password in the config. |
| Cloudflare shows a browser login | Complete that login yourself, then let SSH continue. |
| macOS blocks cloudflared | Use **Privacy & Security > Open Anyway** after removing quarantine. |
| Missing `/config/*.config` or required variables | Request access to the configured workshop environment; do not paste secrets into chat. |
| VSS HTTP 401 | Log in again using the existing VM configuration. Check the account configuration if login itself fails. |
| Empty search results | Validate filters and check indexing progress with `retrieval-dashboard`. |
| GPU HTTP 401 or 403 | Check the configured `GPU_BEARER_TOKEN`; the VSS JWT is a different credential. |
| VastDB 403 | Confirm the request stays inside the team's configured bucket. |

For a live-stack blocker, use [`ask-cosmos`](../.agents/skills/ask-cosmos/SKILL.md)
to check health and prepare a redacted support note. It does not send the note.
Keep passwords, access keys, JWTs, GPU tokens, and token-bearing playback URLs
out of logs and shared notes. Leave the shared DataEngine ingest pipeline as
deployed.
