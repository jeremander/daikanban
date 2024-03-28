import re

from daikanban.interface import BoardInterface
from daikanban.model import Board


def new_interface():
    """Fixture which produces an new empty BoardInterface."""
    board = Board(name='board')
    return BoardInterface(board=board)


class TestInterface:

    def _test_output(self, capsys, commands, expected_output):
        interface = new_interface()
        for cmd in commands:
            interface.evaluate_prompt(cmd)
            s = capsys.readouterr().out
        if isinstance(expected_output, str):
            expected_output = re.compile(re.escape(expected_output))
        assert isinstance(expected_output, re.Pattern)
        assert expected_output.search(s)

    def test_project_show_empty(self, capsys):
        self._test_output(capsys, ['project show'], '[No projects]')

    def test_task_show_empty(self, capsys):
        self._test_output(capsys, ['task show'], '[No tasks]')

    def test_board_show_empty(self, capsys):
        self._test_output(capsys, ['board show'], '[No tasks]')
