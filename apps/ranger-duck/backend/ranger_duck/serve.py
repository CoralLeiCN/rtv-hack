"""Start the single-worker API and its optional durable capture exporter together."""
import argparse
import importlib.util
import os
from pathlib import Path
import subprocess
import sys

import uvicorn

from .config import env_file, env_values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, help='Absolute private config file, shared with the exporter')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=18000)
    args = parser.parse_args()
    if args.env_file is not None:
        os.environ['RANGER_ENV_FILE'] = str(args.env_file)
    try:
        config_path = env_file()
        values = env_values()
    except ValueError as error:
        parser.error(str(error))
    exporting = bool(values.get('RANGER_WEAVE_PROJECT'))
    if exporting and importlib.util.find_spec('weave') is None:
        parser.error('W&B is configured; install the backend with .[capture] before starting.')
    print(f'Configuration file: {config_path}', flush=True)
    exporter = None
    try:
        if exporting:
            # The child loads its own key. Never put credentials in process arguments.
            exporter = subprocess.Popen([sys.executable, '-m', 'ranger_duck.capture', '--follow'])
            print('W&B exporter started; pending captures will resume automatically.', flush=True)
        uvicorn.run('ranger_duck.app:app', host=args.host, port=args.port, workers=1)
    finally:
        if exporter is not None and exporter.poll() is None:
            exporter.terminate()
            try:
                exporter.wait(timeout=10)
            except subprocess.TimeoutExpired:
                exporter.kill()
                exporter.wait()


if __name__ == '__main__':
    main()
