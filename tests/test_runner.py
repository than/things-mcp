import pytest

from things_mcp import runner


def test_run_url_invokes_open(monkeypatch):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["kwargs"] = kwargs

        class R:
            returncode = 0
            stderr = b""

        return R()

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    runner.run_url("things:///add?title=x")
    assert seen["cmd"][0] == "open"
    assert seen["cmd"][-1] == "things:///add?title=x"


def test_run_url_raises_on_failure(monkeypatch):
    def fake_run(cmd, **kwargs):
        class R:
            returncode = 1
            stderr = b"boom"

        return R()

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    with pytest.raises(runner.RunnerError):
        runner.run_url("things:///add?title=x")


def test_run_url_missing_open_raises_runner_error(monkeypatch):
    def fake_run(cmd, **kwargs):
        raise FileNotFoundError("open")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    with pytest.raises(runner.RunnerError):
        runner.run_url("things:///add?title=x")
