#
# voice-skill-sdk
#
# (C) 2021, Deutsche Telekom AG
#
# This file is distributed under the terms of the MIT license.
# For details see the file LICENSE in the top directory.
#

import sys
import pathlib
import pkg_resources
from argparse import Namespace
from unittest import mock

import pytest
from pytest import CaptureFixture

from skill_sdk.__main__ import main
from skill_sdk.cli import import_module_app, develop, init, run, version, DEFAULT_MODULE
from skill_sdk.utils.util import run_until_complete

APP = "app:app"


@pytest.fixture
def debug_logging(monkeypatch):
    from skill_sdk import log
    from skill_sdk.config import settings

    monkeypatch.setattr(settings, "LOG_LEVEL", "DEBUG")
    monkeypatch.setattr(settings, "LOG_FORMAT", "human")
    log.setup_logging()
    return True


@pytest.fixture
def change_dir(monkeypatch):
    """Set current dir to the path of `scaffold` project"""

    scaffold_path = pkg_resources.resource_filename(init.__name__, "scaffold")
    monkeypatch.chdir(scaffold_path)
    cwd = pathlib.Path(scaffold_path).absolute().__str__()
    if cwd not in sys.path:
        monkeypatch.syspath_prepend(cwd)
    return scaffold_path


@pytest.fixture
def app(change_dir):
    _, app = import_module_app(APP)
    yield app
    app.close()

    # Cleanup: remove imported modules
    del sys.modules["app"]
    del sys.modules["impl"]


def test_import_module_app():

    sdk, _ = import_module_app("skill_sdk")
    import skill_sdk

    assert sdk is skill_sdk

    cli, _ = import_module_app("test_cli.py")
    import test_cli

    assert cli is test_cli


def test_develop(debug_logging, mocker, app):

    uv = mocker.patch.object(develop, "uvicorn")

    assert list(app.intents.keys()) == ["SMALLTALK__GREETINGS"]

    develop.execute(Namespace(module=APP))
    uv.run.assert_called_once_with(app, port=4242)


def test_develop_empty_project(tmpdir, mocker, monkeypatch):

    uv = mocker.patch.object(develop, "uvicorn")
    monkeypatch.chdir(tmpdir)

    develop.execute(Namespace(module=DEFAULT_MODULE))

    assert (tmpdir / DEFAULT_MODULE).exists()
    uv.run.assert_called_once_with(mock.ANY, port=4242)

    # Cleanup: remove imported module
    del sys.modules["impl"]


def test_run(debug_logging, mocker, app):

    uv = mocker.patch.object(run, "uvicorn")
    assert list(app.intents.keys()) == ["SMALLTALK__GREETINGS"]

    run.execute(Namespace(module=APP))
    uv.run.assert_called_once_with(app, port=4242)


def test_version(capsys: CaptureFixture, app):
    version.execute(Namespace())

    out = capsys.readouterr()
    assert "0.1" in out.out


def test_with_env_file(capsys: CaptureFixture, change_dir, monkeypatch):

    dev = pathlib.Path(".env.dev")
    dev.write_text("SKILL_VERSION = 0.1a0")
    version.execute(Namespace(module=DEFAULT_MODULE, env_file=".env.dev"))
    out = capsys.readouterr()
    assert "0.1a0" in out.out
    dev.unlink()

    prod = pathlib.Path(".env.prod")
    prod.write_text("SKILL_VERSION = 1.0")
    version.execute(Namespace(module=DEFAULT_MODULE, env_file=".env.prod"))
    out = capsys.readouterr()
    assert "1.0" in out.out
    prod.unlink()


def test_init(tmpdir):

    init.execute(Namespace(out=tmpdir))

    required_files = [
        "impl/__init__.py",
        "impl/test_impl.py",
        "locale/de.po",
        "locale/en.po",
        "locale/fr.po",
        "scripts/develop",
        "scripts/run",
        "scripts/test",
        "scripts/version",
        "app.py",
        "Dockerfile",
        "README.md",
        "requirements.txt",
        "requirements-dev.txt",
        "skill.conf",
    ]
    assert all((pathlib.Path(tmpdir) / file).exists() for file in required_files)


def test_scaffold(app):
    """Run scaffold project testing suite"""

    response = run_until_complete(app.test_intent("SMALLTALK__GREETINGS"))
    assert response.text == "HELLOAPP_HELLO"

    pytest.main(["tests"])


def test_main(app, change_dir, mocker, monkeypatch):
    uv = mocker.patch.object(run, "uvicorn")
    monkeypatch.setattr("sys.argv", ["vs", "run", APP])
    monkeypatch.setenv("LOG_FORMAT", "gelf")
    main()
    uv.run.assert_called_once_with(mock.ANY, port=4242)
