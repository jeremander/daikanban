from contextlib import suppress

import pytest

from daikanban.interface import BoardInterface, parse_string_set
from daikanban.model import Board, Task

from . import match_patterns, patch_stdin


def new_board():
    return Board(name='board')


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

    def _test_output(self, capsys, monkeypatch, user_input, expected_output, board=None):
        class MockBoardInterface(BoardInterface):
            def save_board(self) -> None:
                # do not attempt to save board to a file
                pass
        board = board or new_board()
        interface = MockBoardInterface(board=board)
        for (command, prompt_input) in user_input:
            if prompt_input:
                assert isinstance(prompt_input, list)
                patch_stdin(monkeypatch, ''.join(f'{line}\n' for line in prompt_input))
            try:
                interface.evaluate_prompt(command)
            except EOFError:
                match_patterns(expected_output, capsys.readouterr().out)
                raise
            s = capsys.readouterr().out
        match_patterns(expected_output, s)

    # PROJECT

    def test_project_show_empty(self, capsys):
        self._test_output(capsys, None, [('project show', None)], r'\[No projects\]')

    def test_project_new(self, capsys, monkeypatch):
        user_input = [('project new', ['proj', 'My project.', '']), ('project show', None)]
        outputs = [self._table_row(row) for row in [['id', 'name', 'created', '# tasks'], ['0', 'proj', '.*', '0']]]
        self._test_output(capsys, monkeypatch, user_input, outputs)

    # TASK

    def test_task_show_empty(self, capsys):
        self._test_output(capsys, None, [('task show', None)], r'\[No tasks\]')

    def test_task_new(self, capsys, monkeypatch):
        user_input = [('task new', ['task', 'My task.', '', '7', '', '', '', '']), ('task show', None)]
        outputs = [self._table_row(row) for row in [['id', 'name', 'pri…ty', 'create', 'status'], ['0', 'task', '7', '.*', 'todo']]]
        self._test_output(capsys, monkeypatch, user_input, outputs)

    def test_task_new_another(self, capsys, monkeypatch):
        board = new_board()
        board.create_task(Task(name='task'))
        # attempt to add duplicate task
        user_input = [('task new', ['task'])]
        with suppress(EOFError):
            self._test_output(capsys, monkeypatch, user_input, "Duplicate task name 'task'", board=board)
        # add a task with a unique name
        user_input = [('task new', ['task2'] + [''] * 7)]
        self._test_output(capsys, monkeypatch, user_input, 'Created new task task2 with ID 1', board=board)

    # BOARD

    def test_board_show_empty(self, capsys):
        self._test_output(capsys, None, [('board show', None)], r'\[No tasks\]')

    def test_board_show_one_task(self, capsys, monkeypatch):
        user_input = [('task new', ['task', 'My task.', '', '7', '', '', '', '']), ('board show', None)]
        outputs = [self._table_row(row) for row in [['id', 'name', 'score'], ['0', 'task', '.*']]]
        self._test_output(capsys, monkeypatch, user_input, outputs)
