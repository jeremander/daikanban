from contextlib import suppress

from pydantic_core import Url
import pytest

from daikanban.config import get_config
from daikanban.interface import BoardInterface, parse_string_set
from daikanban.model import Board, Project, Task, TaskStatusAction, TaskStatusError
from daikanban.utils import UserInputError, get_current_time

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

    def _test_output(self, capsys, monkeypatch, user_input, out=None, err=None, board=None):
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
                res = capsys.readouterr()
                match_patterns(out, res.out)
                match_patterns(err, res.err)
                raise
        res = capsys.readouterr()
        match_patterns(out, res.out)
        match_patterns(err, res.err)

    # PROJECT

    def test_project_show_empty(self, capsys):
        self._test_output(capsys, None, [('project show', None)], r'\[No projects\]')

    def test_project_new(self, capsys, monkeypatch):
        user_input = [('project new', ['proj', 'My project.', '']), ('project show', None)]
        outputs = [self._table_row(row) for row in [['id', 'name', 'created', '# tasks'], ['0', 'proj', '.*', '0']]]
        self._test_output(capsys, monkeypatch, user_input, outputs)
        # create project with an invalid name
        user_input = [('project new 123', [])]
        with pytest.raises(UserInputError, match='Project name .* is invalid, must have at least one letter'):
            self._test_output(capsys, monkeypatch, user_input)
        user_input = [('project new', ['123', 'a123', '', ''])]
        self._test_output(capsys, monkeypatch, user_input, out='Project name .* is invalid, must have at least one letter')

    def test_project_new_another(self, capsys, monkeypatch):
        board = new_board()
        board.create_project(Project(name='proj'))
        # add a project with a unique name
        user_input = [('project new', ['proj1'] + [''] * 2)]
        self._test_output(capsys, monkeypatch, user_input, out='Created new project proj1 with ID 1', board=board)
        assert board.get_project(1).name == 'proj1'
        # add a project with the name given rather than prompted
        user_input = [('project new proj2', [''] * 2)]
        self._test_output(capsys, monkeypatch, user_input, out='Created new project proj2 with ID 2', board=board)
        assert board.get_project(2).name == 'proj2'
        # attempt to add project with a duplicate name
        user_input = [('project new proj', [''] * 2)]
        self._test_output(capsys, monkeypatch, user_input, out='Created new project proj with ID 3', err='Duplicate project name', board=board)

    def test_project_set(self, capsys, monkeypatch):
        now = get_current_time()
        board = new_board()
        board.create_project(Project(name='proj'))
        # set an invalid field
        user_input = [('project set 0 fake-field value', None)]
        with pytest.raises(UserInputError, match="Unknown field 'fake-field'"):
            self._test_output(capsys, monkeypatch, user_input, board=board)
        # set field on a nonexistent project
        user_input = [('project set 1 name proj1', None)]
        with pytest.raises(UserInputError, match='Project with ID 1 not found'):
            self._test_output(capsys, monkeypatch, user_input, board=board)
        # set the name
        user_input = [('project set 0 name proj0', None)]
        self._test_output(capsys, monkeypatch, user_input, "Updated field 'name'", board=board)
        # set the name with '=' expression
        user_input = [('project set 0 name=proj1', None)]
        self._test_output(capsys, monkeypatch, user_input, "Updated field 'name'", board=board)
        assert board.get_project(0).name == 'proj1'
        user_input = [('project set 0 name="new project"', None)]
        self._test_output(capsys, monkeypatch, user_input, "Updated field 'name'", board=board)
        assert board.get_project(0).name == 'new project'
        # attempt to set an invalid name
        user_input = [('project set 0 name=123', None)]
        with pytest.raises(UserInputError, match='Project name .*123.* is invalid, must have at least one letter'):
            self._test_output(capsys, monkeypatch, user_input, board=board)
        # NOTE: currently, extra args are permitted but ignored
        user_input = [('project set 0 name=proj0 other stuff', None)]
        self._test_output(capsys, monkeypatch, user_input, "Updated field 'name'", board=board)
        proj = board.get_project(0)
        assert proj.name == 'proj0'
        assert proj.description is None
        # set description to empty string (gets converted to None)
        for c in ["'", '"']:
            user_input = [(f'project set 0 description {c}{c}', None)]
            self._test_output(capsys, monkeypatch, user_input, "Updated field 'description'", board=board)
            assert board.get_project(0).description is None
        # set description to null
        user_input = [('project set 0 description', None)]
        self._test_output(capsys, monkeypatch, user_input, "Updated field 'description'", board=board)
        assert board.get_project(0).description is None
        # set creation time to valid value
        user_input = [('project set 0 created_time yesterday', None)]
        self._test_output(capsys, monkeypatch, user_input, "Updated field 'created_time'", board=board)
        assert board.get_project(0).created_time < now
        # set the set of links
        assert board.get_project(0).links is None
        user_input = [('project set 0 links ""', None)]
        self._test_output(capsys, monkeypatch, user_input, "Updated field 'links'", board=board)
        assert board.get_project(0).links is None  # empty set becomes None
        user_input = [('project set 0 links link1', None)]
        with pytest.raises(UserInputError, match='Invalid URL'):
            self._test_output(capsys, monkeypatch, user_input, board=board)
        user_input = [('project set 0 links link1.com', None)]
        self._test_output(capsys, monkeypatch, user_input, "Updated field 'links'", board=board)
        assert board.get_project(0).links == {Url('https://link1.com')}
        for links in ['link1.com,link2.org', '" link1.com,  link2.org"']:
            user_input = [(f'project set 0 links {links}', None)]
            self._test_output(capsys, monkeypatch, user_input, "Updated field 'links'", board=board)
            assert board.get_project(0).links == {Url('https://link1.com'), Url('https://link2.org')}
        user_input = [('project set 0 links', None)]
        self._test_output(capsys, monkeypatch, user_input, "Updated field 'links'", board=board)
        assert board.get_project(0).links is None
        # attempt to set fields to invalid values
        user_input = [('project set 0 name', None)]
        with pytest.raises(UserInputError, match='Input should be a valid string'):
            self._test_output(capsys, monkeypatch, user_input, board=board)
        user_input = [('project set 0 created_time', None)]
        with pytest.raises(UserInputError, match='Input should be a valid datetime'):
            self._test_output(capsys, monkeypatch, user_input, board=board)
        user_input = [('project set 0 created_time abc', None)]
        with pytest.raises(UserInputError, match="Invalid time 'abc'"):
            self._test_output(capsys, monkeypatch, user_input, board=board)
        # set duplicate project name
        board.create_project(Project(name='proj'))
        # set project parent
        user_input = [('project set 1 parent 0', None)]
        self._test_output(capsys, monkeypatch, user_input, out="Updated field 'parent' for project proj with ID 1", board=board)
        user_input = [('project set 1 parent proj0', None)]
        self._test_output(capsys, monkeypatch, user_input, out="Updated field 'parent' for project proj with ID 1", board=board)
        # set project parent to invalid value
        user_input = [('project set 1 parent 2', None)]
        with pytest.raises(UserInputError, match='Project with ID 2 not found'):
            self._test_output(capsys, monkeypatch, user_input, board=board)
        user_input = [('project set 1 parent fake', None)]
        with pytest.raises(UserInputError, match='Invalid project name'):
            self._test_output(capsys, monkeypatch, user_input, board=board)
        # rename project to duplicate another one
        user_input = [('project set 1 name proj0', None)]
        self._test_output(capsys, monkeypatch, user_input, err='Duplicate project name', board=board)
        # attempt to set the project ID
        user_input = [('project set 1 project_id 2', None)]
        with pytest.raises(UserInputError, match="Field 'project_id' cannot be updated"):
            self._test_output(capsys, monkeypatch, user_input, board=board)
        # attempt to set an invalid field
        user_input = [('project set 1 fake abc', None)]
        with pytest.raises(UserInputError, match="Unknown field 'fake'"):
            self._test_output(capsys, monkeypatch, user_input, board=board)
        # attempt to set parent to ambiguous project name
        user_input = [('project set 1 parent proj0', None)]
        with pytest.raises(UserInputError, match="Ambiguous project name 'proj0'"):
            self._test_output(capsys, monkeypatch, user_input, board=board)

    # TASK

    def test_task_show_empty(self, capsys):
        self._test_output(capsys, None, [('task show', None)], r'\[No tasks\]')

    def test_task_new(self, capsys, monkeypatch):
        user_input = [('task new', ['task', 'My task.', '', '7', '', '', '', '']), ('task show', None)]
        outputs = [self._table_row(row) for row in [['id', 'name', 'pri…ty', 'create', 'status'], ['0', 'task', '7', '.*', 'todo']]]
        self._test_output(capsys, monkeypatch, user_input, outputs)
        # create task with an invalid name
        user_input = [('task new 123', [])]
        with pytest.raises(UserInputError, match='Task name .* is invalid, must have at least one letter'):
            self._test_output(capsys, monkeypatch, user_input)
        user_input = [('task new', ['123', 'a123', '', '', '', '', '', ''])]
        self._test_output(capsys, monkeypatch, user_input, out='Task name .* is invalid, must have at least one letter')

    def test_task_new_another(self, capsys, monkeypatch):
        board = new_board()
        board.create_task(Task(name='task'))
        # add a task with a unique name
        user_input = [('task new', ['task1'] + [''] * 7)]
        self._test_output(capsys, monkeypatch, user_input, out='Created new task task1 with ID 1', board=board)
        assert board.get_task(1).name == 'task1'
        # add a task with the name given rather than prompted
        user_input = [('task new task2', [''] * 7)]
        self._test_output(capsys, monkeypatch, user_input, out='Created new task task2 with ID 2', board=board)
        assert board.get_task(2).name == 'task2'
        # add task with duplicate name
        user_input = [('task new task', [''] * 7)]
        self._test_output(capsys, monkeypatch, user_input, out='Created new task task with ID 3', err='Duplicate task name', board=board)

    def test_task_begin(self, capsys, monkeypatch):
        now = get_current_time()
        board = new_board()
        board.create_task(Task(name='task0'))
        user_input = [('task begin 0', [''])]
        self._test_output(capsys, monkeypatch, user_input, r'\[0\] to active state', board=board)
        task = board.get_task(0)
        assert task.first_started_time > task.created_time
        # attempt to start a task before its creation time, but decline to
        board.create_task(Task(name='task1'))
        user_input = [('task begin 1', ['yesterday', 'n', 'now'])]
        self._test_output(capsys, monkeypatch, user_input, r'\[1\] to active state', board=board)
        task = board.get_task(1)
        assert task.first_started_time > task.created_time
        # start a task before its creation time, overwrite its creation time
        board.create_task(Task(name='task2'))
        user_input = [('task begin 2', ['yesterday', 'y'])]
        self._test_output(capsys, monkeypatch, user_input, r'\[2\] to active state', board=board)
        task = board.get_task(2)
        assert task.first_started_time == task.created_time
        assert task.first_started_time < now

    def test_task_complete(self, capsys, monkeypatch):
        now = get_current_time()
        board = new_board()
        # complete a task without starting it
        board.create_task(Task(name='task0'))
        user_input = [('task complete 0', ['now', 'now'])]
        self._test_output(capsys, monkeypatch, user_input, r'\[0\] to complete state', board=board)
        task = board.get_task(0)
        assert task.created_time > now
        assert task.first_started_time > task.created_time
        assert task.completed_time > task.first_started_time
        # complete task before start time, but after creation time
        board.create_task(Task(name='task1'))
        user_input = [('task complete 1', ['in 2 days', 'in 1 day'])]
        with pytest.raises(TaskStatusError, match='cannot complete a task before its last started time'):
            self._test_output(capsys, monkeypatch, user_input, board=board)
        # attempt to create a task before creation time, but decline to
        board.create_task(Task(name='task2'))
        user_input = [('task complete 2', ['yesterday', 'n'])]
        with suppress(EOFError):
            self._test_output(capsys, monkeypatch, user_input, 'Cannot start a task before its creation time', board=board)
        # complete task before creation time, but after start time
        board.create_task(Task(name='task3'))
        user_input = [('task complete 3', ['2 days ago', 'y', 'yesterday'])]
        outputs = ['Set creation time', r'\[3\] to complete state']
        self._test_output(capsys, monkeypatch, user_input, outputs, board=board)
        task = board.get_task(3)
        assert task.created_time < now
        assert task.first_started_time == task.created_time
        assert task.completed_time > task.first_started_time
        # complete task before creation time and before start time
        board.create_task(Task(name='task3'))
        user_input = [('task complete 4', ['yesterday', 'y', '2 days ago', 'y'])]
        with pytest.raises(TaskStatusError, match='cannot complete a task before its last started time'):
            self._test_output(capsys, monkeypatch, user_input, board=board)

    def test_task_set(self, capsys, monkeypatch):
        now = get_current_time()
        board = new_board()
        board.create_task(Task(name='task', description='task'))
        # set the name
        user_input = [('task set 0 name task0', None)]
        self._test_output(capsys, monkeypatch, user_input, "Updated field 'name'", board=board)
        # set the name with '=' expression
        user_input = [('task set 0 name=task1', None)]
        self._test_output(capsys, monkeypatch, user_input, "Updated field 'name'", board=board)
        assert board.get_task(0).name == 'task1'
        user_input = [('task set 0 name="new task"', None)]
        self._test_output(capsys, monkeypatch, user_input, "Updated field 'name'", board=board)
        assert board.get_task(0).name == 'new task'
        # NOTE: currently, extra args are permitted but ignored
        user_input = [('task set 0 name=task0 other stuff', None)]
        self._test_output(capsys, monkeypatch, user_input, "Updated field 'name'", board=board)
        task = board.get_task(0)
        assert task.name == 'task0'
        assert task.description == 'task'
        # attempt to set an invalid name
        user_input = [('task set 0 name=123', None)]
        with pytest.raises(UserInputError, match='Task name .*123.* is invalid, must have at least one letter'):
            self._test_output(capsys, monkeypatch, user_input, board=board)
        # set description to null
        user_input = [('task set 0 description', None)]
        self._test_output(capsys, monkeypatch, user_input, "Updated field 'description'", board=board)
        assert board.get_task(0).description is None
        # attempt to set start time earlier than created time
        user_input = [('task set 0 first_started_time yesterday', None)]
        with pytest.raises(UserInputError, match='Task start time cannot precede created time'):
            self._test_output(capsys, monkeypatch, user_input, board=board)
        # attempt to set created time later than start time
        user_input = [('task set 0 first_started_time tomorrow', None)]
        self._test_output(capsys, monkeypatch, user_input, "Updated field 'first_started_time'", board=board)
        assert board.get_task(0).first_started_time > now
        user_input = [('task set 0 created_time "in two days"', None)]
        with pytest.raises(UserInputError, match='Task start time cannot precede created time'):
            self._test_output(capsys, monkeypatch, user_input, board=board)
        # attempt to set a computed field
        user_input = [('task set 0 status todo', None)]
        with pytest.raises(UserInputError, match="Field 'status' cannot be updated"):
            self._test_output(capsys, monkeypatch, user_input, "Updated field 'description'", board=board)
        # attempt to set fields to invalid values
        user_input = [('task set 0 name', None)]
        with pytest.raises(UserInputError, match='Input should be a valid string'):
            self._test_output(capsys, monkeypatch, user_input, board=board)
        # attempt to set duplicate task name
        board.create_task(Task(name='task'))
        user_input = [('task set 1 name task0', None)]
        self._test_output(capsys, monkeypatch, user_input, out="Updated field 'name'", err='Duplicate task name', board=board)
        # attempt to set the task ID
        user_input = [('task set 1 task_id 2', None)]
        with pytest.raises(UserInputError, match="Field 'task_id' cannot be updated"):
            self._test_output(capsys, monkeypatch, user_input, board=board)
        # set the project ID to an invalid project
        user_input = [('task set 1 project_id 0', None)]
        with pytest.raises(UserInputError, match='Project with ID 0 not found'):
            self._test_output(capsys, monkeypatch, user_input, board=board)
        # set the project ID to a valid project
        assert board.create_project(Project(name='proj')) == 0
        self._test_output(capsys, monkeypatch, user_input, out="Updated field 'project_id' for task task0 with ID 1", board=board)
        # update the project ID via "project" instead of "project_id"
        user_input = [('task set 1 project 0', None)]
        self._test_output(capsys, monkeypatch, user_input, out="Updated field 'project_id' for task task0 with ID 1", board=board)
        # update the project ID via its name
        user_input = [('task set 1 project proj', None)]
        self._test_output(capsys, monkeypatch, user_input, out="Updated field 'project_id' for task task0 with ID 1", board=board)
        # attempt to use a project name instead of ID with "project_id"
        user_input = [('task set 1 project_id proj', None)]
        with pytest.raises(UserInputError, match="Invalid project ID 'proj'"):
            self._test_output(capsys, monkeypatch, user_input, board=board)
        # unset the project ID
        for cmd in ['task set 1 project', 'task set 1 project_id', 'task set 1 project=', "task set 1 project=''", "task set 1 project_id=''"]:
            user_input = [(cmd, None)]
            self._test_output(capsys, monkeypatch, user_input, out="Updated field 'project_id' for task task0 with ID 1", board=board)
        # set task parent
        user_input = [('task set 1 parent 0', None)]
        self._test_output(capsys, monkeypatch, user_input, out="Updated field 'parent' for task task0 with ID 1", board=board)
        # set task parent to ambiguous task name
        user_input = [('task set 1 parent task0', None)]
        with pytest.raises(UserInputError, match="Ambiguous task name 'task0'"):
            self._test_output(capsys, monkeypatch, user_input, board=board)
        # name 'task' matches two instances of 'task0' (fuzzily)
        user_input = [('task set 1 parent task', None)]
        with pytest.raises(UserInputError, match="Ambiguous task name 'task'"):
            self._test_output(capsys, monkeypatch, user_input, board=board)
        # set blocking tasks
        user_input = [('task set 1 blocked_by 0', None)]
        self._test_output(capsys, monkeypatch, user_input, out="Updated field 'blocked_by' for task task0 with ID 1", board=board)
        assert board.get_task(1).blocked_by == {0}
        user_input = [('task set 1 blocked_by 0,1', None)]
        self._test_output(capsys, monkeypatch, user_input, out="Updated field 'blocked_by' for task task0 with ID 1", board=board)
        assert board.get_task(1).blocked_by == {0, 1}
        user_input = [('task set 1 blocked_by 2', None)]
        with pytest.raises(UserInputError, match="Task with ID 2 not found"):
            self._test_output(capsys, monkeypatch, user_input, board=board)
        board.update_task(1, name='task1')
        user_input = [('task set 1 blocked_by 0,task1', None)]
        self._test_output(capsys, monkeypatch, user_input, out="Updated field 'blocked_by' for task task1 with ID 1", board=board)
        assert board.get_task(1).blocked_by == {0, 1}

    # BOARD

    def test_board_show_empty(self, capsys):
        self._test_output(capsys, None, [('board show', None)], r'\[No tasks\]')

    def test_board_show_one_task(self, capsys, monkeypatch):
        board = new_board()
        user_input = [('task new', ['task', 'My task.', '', '7', '', '', '', '']), ('board show', None)]
        outputs = [r'todo \(1\)'] + [self._table_row(row) for row in [['id', 'name', 'score'], ['0', 'task', '.*']]]
        self._test_output(capsys, monkeypatch, user_input, outputs, board=board)
        user_input = [('task begin 0', ['']), ('board show', None)]
        outputs = [r'active \(1\)', 'Score:']
        self._test_output(capsys, monkeypatch, user_input, outputs, board=board)
        user_input = [('task complete 0', ['']), ('board show', None)]
        outputs = [r'complete \(1\)', 'last', self._table_row(['id', 'name', 'completed'])]
        self._test_output(capsys, monkeypatch, user_input, outputs, board=board)

    def test_board_sort_tasks(self, capsys, monkeypatch):
        board = new_board()
        for i in range(3):
            board.create_task(Task(name=f'task{i}'))
            board.apply_status_action(i, TaskStatusAction.start)
        board.apply_status_action(1, TaskStatusAction.pause)
        interface = BoardInterface(board=board)
        cfg = get_config()
        task_rows_by_col = interface._get_task_rows_by_column()
        assert list(task_rows_by_col) == ['active']
        names = [row.name for row in task_rows_by_col['active']]
        # active tasks are shown before paused
        assert names == ['task0', 'task2', 'task1 ⏸️ ']
        # sort tasks by name instead
        cfg.display.columns['active'].sort_by = 'name'
        interface = BoardInterface(board=board, config=cfg)
        task_rows_by_col = interface._get_task_rows_by_column()
        names = [row.name for row in task_rows_by_col['active']]
        # status column should *not* be shown
        with pytest.raises(AssertionError, match="pattern 'status' not found"):
            self._test_output(capsys, monkeypatch, [('board show', None)], ['status'], board=board)
