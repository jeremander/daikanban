import json
from pathlib import Path
import sys

import pytest

from daikanban import __version__
from daikanban.main import APP
from daikanban.model import Board

from . import match_patterns


EXEC_PATH = Path(__file__).parents[1] / 'daikanban' / 'main.py'


class TestMain:

    def _test_main(self, capsys, monkeypatch, args, patterns, exact=False):
        argv = [sys.executable] + args
        monkeypatch.setattr('sys.argv', argv)
        try:
            APP()
        except SystemExit as e:
            assert e.code == 0  # noqa: PT017
            match_patterns(patterns, capsys.readouterr().out, exact=exact)
        else:
            pytest.fail('app should raise SystemExit')

    def test_help(self, capsys, monkeypatch):
        patterns = ['Commands', r'--help\s+-h\s+Show this message and exit.', r'new\s+create new board']
        for cmd in [[], ['--help']]:
            self._test_main(capsys, monkeypatch, cmd, patterns)

    def test_version(self, capsys, monkeypatch):
        self._test_main(capsys, monkeypatch, ['--version'], f'{__version__}\n', exact=True)

    def test_schema(self, capsys, monkeypatch):
        # use regular print instead of rich.print
        monkeypatch.setattr('daikanban.interface.print', print)
        schema = json.dumps(Board.model_json_schema(mode='serialization'), indent=2) + '\n'
        self._test_main(capsys, monkeypatch, ['schema'], schema, exact=True)
