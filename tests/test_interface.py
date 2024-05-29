import re

import pytest

from daikanban.interface import BoardInterface, parse_string_set
from daikanban.model import Board

from . import patch_stdin


@pytest.mark.parametrize(['s', 'parsed'],[
    ('', None),
    ('a', {'a'}),
    (' a ', {'a'}),
    ('a,b', {'a', 'b'}),
    ('a, b', {'a', 'b'}),
    ('a,\tb', {'a', 'b'}),
    ('" a ",b', {'a', 'b'}),
    ('a b', {'a b'}),
    ('"a, b"', {'a, b'}),
    ("'a, b'", {"'a", "b'"}),
])
def test_parse_string_set(s, parsed):
    assert parse_string_set(s) == parsed


class TestInterface:

    @staticmethod
    def _table_row(cells):
        return r'[│┃]\s*' + r'\s*[│┃]\s*'.join(cells) + r'\s*[│┃]'

    def _test_output(self, capsys, monkeypatch, user_input, expected_output):
        class MockBoardInterface(BoardInterface):
            def save_board(self) -> None:
                pass
        interface = MockBoardInterface(board=Board(name='board'))
        for (command, prompt_input) in user_input:
            if prompt_input:
                assert isinstance(prompt_input, list)
                patch_stdin(monkeypatch, ''.join(f'{line}\n' for line in prompt_input))
            interface.evaluate_prompt(command)
            s = capsys.readouterr().out
        if not isinstance(expected_output, list):
            expected_output = [expected_output]
        for output in expected_output:
            if isinstance(output, str):
                output = re.compile(output)
            assert isinstance(output, re.Pattern)
            assert output.search(s)

    def test_project_show_empty(self, capsys):
        self._test_output(capsys, None, [('project show', None)], r'\[No projects\]')

    def test_project_show_one(self, capsys, monkeypatch):
        user_input = [('project new', ['proj', 'My project.', '']), ('project show', None)]
        outputs = [self._table_row(row) for row in [['id', 'name', 'created', '# tasks'], ['0', 'proj', '.*', '0']]]
        self._test_output(capsys, monkeypatch, user_input, outputs)

    def test_task_show_empty(self, capsys):
        self._test_output(capsys, None, [('task show', None)], r'\[No tasks\]')

    def test_task_show_one(self, capsys, monkeypatch):
        user_input = [('task new', ['task', 'My task.', '', '7', '', '', '', '']), ('task show', None)]
        outputs = [self._table_row(row) for row in [['id', 'name', 'pri…ty', 'create', 'status'], ['0', 'task', '7', '.*', 'todo']]]
        self._test_output(capsys, monkeypatch, user_input, outputs)

    def test_board_show_empty(self, capsys):
        self._test_output(capsys, None, [('board show', None)], r'\[No tasks\]')

    def test_board_show_one_task(self, capsys, monkeypatch):
        user_input = [('task new', ['task', 'My task.', '', '7', '', '', '', '']), ('board show', None)]
        outputs = [self._table_row(row) for row in [['id', 'name', 'score'], ['0', 'task', '.*']]]
        self._test_output(capsys, monkeypatch, user_input, outputs)
