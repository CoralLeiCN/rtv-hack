"""Private, durable event capture; no credentials or video bytes are recorded."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import secrets
import time

_run = ContextVar('capture_run', default=None)
_sensitive = re.compile(r'^(authorization|cookie|set.cookie|password|(?:x.)?api.key|access.token|refresh.token|id.token|token|secret)$', re.I)
_url = re.compile(r'https?://[^\s<>"\']+')


class Capture:
    def __init__(self, directory: Path | None = None, secrets_to_redact=()):
        self.directory = directory
        self.secrets = tuple(value for value in secrets_to_redact if value)
        self.salt = secrets.token_bytes(32)
        self.failed = False

    def run_id(self, owner, identity):
        return hashlib.sha256(self.salt + f'{owner}\0{identity}'.encode()).hexdigest()[:32]

    @contextmanager
    def scope(self, run_id):
        token = _run.set(run_id)
        try:
            yield
        finally:
            _run.reset(token)

    def clean(self, value):
        if isinstance(value, dict):
            return {str(k): '[redacted]' if _sensitive.match(str(k)) else self.clean(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self.clean(v) for v in value]
        if isinstance(value, str):
            # Keep stable source paths; drop URL credentials, query signatures and fragments.
            from urllib.parse import urlsplit, urlunsplit
            def strip_url(match):
                try:
                    url = urlsplit(match[0])
                    return urlunsplit((url.scheme, url.netloc.rsplit('@', 1)[-1], url.path, '', ''))
                except ValueError:
                    return '[redacted-url]'
            value = _url.sub(strip_url, value)
            value = re.sub(r'(?i)\bBearer\s+\S+', 'Bearer [redacted]', value)
            value = re.sub(r'\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b', '[redacted-token]', value)
            for secret in self.secrets:
                value = value.replace(secret, '[redacted]')
            return value
        return value

    def emit(self, kind, inputs=None, output=None, *, run_id=None, **attributes):
        if self.directory is None:
            return
        now = datetime.now(timezone.utc)
        record = self.clean({'schema_version': 1, 'event_id': secrets.token_hex(16),
            'run_id': run_id or _run.get(), 'timestamp': now.isoformat(), 'kind': kind,
            'inputs': inputs, 'output': output, 'attributes': attributes})
        try:
            self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            path = self.directory / f'{now:%Y-%m-%d}.jsonl'
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'a', encoding='utf-8') as stream:
                os.fchmod(stream.fileno(), 0o600)
                stream.write(json.dumps(record, ensure_ascii=False) + '\n')
                stream.flush()
                os.fsync(stream.fileno())
        except (OSError, ValueError, TypeError):
            self.failed = True
            # Never log the payload, path, or exception (may contain private data).
            logging.getLogger(__name__).error('Capture write failed; check private capture storage.')

    async def call(self, kind, inputs, operation):
        started = time.monotonic()
        self.emit(kind + '.started', inputs)
        try:
            output = await operation()
        except BaseException as error:
            self.emit(kind + '.failed', inputs, error_type=type(error).__name__,
                      elapsed_ms=round((time.monotonic() - started) * 1000))
            raise
        self.emit(kind + '.completed', inputs,
                  output.model_dump(mode='json') if hasattr(output, 'model_dump') else output,
                  elapsed_ms=round((time.monotonic() - started) * 1000))
        return output


class CapturedAgent:
    def __init__(self, agent, capture):
        self.agent, self.capture = agent, capture

    @property
    def available(self):
        return self.agent.available

    async def decide(self, context, schema):
        return await self.capture.call('codex.decision',
            {'context': context, 'schema': schema.__name__}, lambda: self.agent.decide(context, schema))


def export_pending(directory, project, weave, client):
    """Acknowledge only calls read back from Weave; leave failed uploads retryable."""
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    checkpoint = directory / ('.weave-' + hashlib.sha256(project.encode()).hexdigest()[:16] + '.acks')
    acknowledged = set(checkpoint.read_text().splitlines()) if checkpoint.exists() else set()
    count = 0
    for path in sorted(directory.glob('*.jsonl')):
        with path.open(encoding='utf-8') as stream:
            for line in stream:
                if not line.endswith('\n'):
                    break  # A live writer may still be appending this event.
                event = json.loads(line)
                if event['event_id'] in acknowledged:
                    continue
                call = weave.log_call(op=event['kind'], inputs=event['inputs'] or {}, output=event['output'],
                    attributes={**event['attributes'], 'event_id': event['event_id'],
                                'run_id': event['run_id'], 'captured_at': event['timestamp']}, use_stack=False)
                client.flush()
                # Flush alone is not a delivery receipt. Check the stored event identity.
                stored = client.get_call(call.id)
                if stored.attributes.get('event_id') != event['event_id']:
                    raise RuntimeError('Capture export was not confirmed')
                fd = os.open(checkpoint, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
                with os.fdopen(fd, 'a') as ack:
                    ack.write(event['event_id'] + '\n')
                    ack.flush()
                    os.fsync(ack.fileno())
                acknowledged.add(event['event_id'])
                count += 1
    return count


def main():
    """Export local captures once, or continuously with --follow."""
    import argparse
    from .config import env_file, env_values, Settings
    parser = argparse.ArgumentParser(description='Export private Ranger Duck captures to W&B Weave.')
    values = env_values()
    parser.add_argument('--directory', type=Path, default=Settings.from_env().capture_dir)
    parser.add_argument('--project', default=values.get('RANGER_WEAVE_PROJECT'), help='W&B entity/project')
    parser.add_argument('--follow', action='store_true', help='Upload new events every two seconds; retry failures')
    args = parser.parse_args()
    if not args.project:
        parser.error('Set RANGER_WEAVE_PROJECT or pass --project ENTITY/PROJECT.')
    # Load only the exporter credential, never forward the archive environment to Weave.
    if values.get('WANDB_API_KEY'):
        os.environ['WANDB_API_KEY'] = values['WANDB_API_KEY']
    import weave
    print(f'Exporter configuration file: {env_file()}', flush=True)
    client = None
    try:
        while True:
            try:
                if client is None:
                    client = weave.init(args.project, settings={'capture_code': False, 'print_call_link': False})
                count = export_pending(args.directory, args.project, weave, client)
                if count or not args.follow:
                    print(f'Confirmed {count} capture events in Weave.', flush=True)
            except Exception:
                # SDK exceptions can include private request payloads.
                print('Capture export failed; local events are retained for retry.', flush=True)
                if not args.follow:
                    raise SystemExit(1) from None
            if not args.follow:
                break
            time.sleep(2)
    except KeyboardInterrupt:
        pass
    finally:
        if client is not None:
            weave.finish()


if __name__ == '__main__':
    main()
