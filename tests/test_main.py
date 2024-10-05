import json
from pathlib import Path
import sys

import pytest

from daikanban import __version__
from daikanban.board import Board
from daikanban.cli.main import APP
from daikanban.config import get_config, user_config_exists, user_config_path, user_dir
from daikanban.utils import get_current_time

from . import make_uuid, match_patterns


EXEC_PATH = Path(__file__).parents[1] / 'daikanban' / 'main.py'


class TestMain:

    def _test_main(self, capsys, args, out_patterns=None, err_patterns=None, exact=False):
        argv = [sys.executable] + args
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr('sys.argv', argv)
            try:
                APP()
            except SystemExit as e:
                assert e.code == 0  # noqa: PT017
                result = capsys.readouterr()
                if out_patterns:
                    match_patterns(out_patterns, result.out, exact=exact)
                if err_patterns:
                    match_patterns(err_patterns, result.err, exact=exact)
            else:
                pytest.fail('app should raise SystemExit')

    @pytest.mark.display
    def test_help(self, capsys):
        """Tests that the help menu is displayed when calling the program with `--help` or with no arguments."""
        patterns = ['Commands', r'--help\s+-h\s+Show this message and exit.', r'new\s+create new board']
        for cmd in [[], ['--help']]:
            self._test_main(capsys, cmd, out_patterns=patterns)

    def test_version(self, capsys):
        """Tests that the --version flag prints out the current version."""
        self._test_main(capsys, ['--version'], f'{__version__}\n', exact=True)

    def test_config(self, capsys, tmpdir, monkeypatch):
        """Tests various 'config' subcommands."""
        tmp_home = Path(tmpdir / 'home')
        monkeypatch.setattr(Path, 'home', lambda: tmp_home)
        assert not user_config_exists()
        p = user_dir()
        assert p == tmp_home / '.daikanban'
        assert not p.exists()
        p.mkdir(parents=True)
        self._test_main(capsys, ['config', 'new'], err_patterns='Saved default config file')
        assert user_config_exists()
        cfg_path = user_config_path()
        self._test_main(capsys, ['config', 'path'], f'{cfg_path}\n', exact=True)
        cfg_str = cfg_path.read_text()
        self._test_main(capsys, ['config', 'show'], f'{cfg_str}\n', exact=True)

    def test_list(self, capsys, use_regular_print, populate_board_dir):
        """Tests the 'list' subcommand, which prints out the board path and list of filenames."""
        board_cfg = get_config().board
        board_dir = board_cfg.board_dir_path
        err = [f'Board directory: {board_dir}\n\n']
        out = ['  * board.json\n    empty_board.json\n    empty_file.JSON\n']
        self._test_main(capsys, ['list'], out_patterns=out, err_patterns=err, exact=True)
        # delete default board
        (board_dir / 'board.json').unlink()
        out = ['  empty_board.json\n  empty_file.JSON\n']
        self._test_main(capsys, ['list'], out_patterns=out, err_patterns=err, exact=True)
        # delete all boards
        for p in board_dir.glob('*'):
            p.unlink()
        err = [err[0] + '[No boards]\n']
        self._test_main(capsys, ['list'], out_patterns=[''], err_patterns=err, exact=True)

    def test_schema(self, capsys, use_regular_print):
        """Tests the 'schema' subcommand which prints the Board JSON schema."""
        schema = json.dumps(Board.json_schema(mode='serialization'), indent=2) + '\n'
        self._test_main(capsys, ['schema'], out_patterns=schema, exact=True)

    def _check_board_equality(self, fmt, board1, board2):
        if fmt == 'daikanban':
            assert board1 == board2
        elif fmt == 'taskwarrior':
            dt = get_current_time()
            def _normalize_project(id_, proj):
                return proj._replace(uuid=make_uuid(id_), description=None, modified_time=dt)
            def _normalize_projects(board):
                return board._replace(projects={id_: _normalize_project(id_, proj) for (id_, proj) in board.projects.items()})
            assert _normalize_projects(board1) == _normalize_projects(board2)

    @pytest.mark.parametrize(['fmt', 'output_ext'], [
        ('daikanban', 'json'),
        ('taskwarrior', 'json'),
    ])
    def test_export_import(self, capsys, test_board, tmp_path, fmt, output_ext):
        """Tests exporting and importing boards to different formats."""
        board_path = tmp_path / 'board.json'
        export_path = tmp_path / f'export.{output_ext}'
        test_board.save(board_path)
        assert board_path.exists()
        self._test_main(capsys, ['export', '-b', str(board_path), '-f', fmt, '-o', str(export_path)], err_patterns=['Exporting to', 'DONE'])
        assert export_path.exists()
        if fmt == 'daikanban':
            assert test_board.to_json_string() == export_path.read_text()
        # save an empty board
        board = Board(name=test_board.name, created_time=test_board.created_time)
        board.save(board_path)
        # import board to an empty board, then save it out
        self._test_main(capsys, ['import', '-f', fmt, '-b', str(board_path), '-i', str(export_path)], err_patterns=['Importing from', 'DONE'])
        board = Board.load(board_path)
        self._check_board_equality(fmt, board, test_board)
