from types import SimpleNamespace

from ranger_duck import serve


def test_each_restart_launches_exporter_with_same_config(tmp_path, monkeypatch):
    config = tmp_path / 'shared.env'
    config.write_text('RANGER_WEAVE_PROJECT=team/project\nWANDB_API_KEY=private-test-key\n')
    monkeypatch.delenv('WANDB_API_KEY', raising=False)
    monkeypatch.setenv('RANGER_ENV_FILE', str(config))
    monkeypatch.setattr('sys.argv', ['ranger-duck-serve', '--env-file', str(config)])
    monkeypatch.setattr(serve.importlib.util, 'find_spec', lambda name: object())
    processes, terminated, loads = [], [], []

    def start(command):
        assert 'private-test-key' not in ' '.join(command)
        loads.append(serve.env_values()['WANDB_API_KEY'])
        process = SimpleNamespace(poll=lambda: None, terminate=lambda: terminated.append(True),
                                  wait=lambda timeout: None)
        processes.append(process)
        return process

    monkeypatch.setattr(serve.subprocess, 'Popen', start)
    monkeypatch.setattr(serve.uvicorn, 'run', lambda *args, **kwargs: None)
    serve.main()
    serve.main()
    assert loads == ['private-test-key', 'private-test-key']
    assert len(processes) == len(terminated) == 2
