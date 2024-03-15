from datetime import datetime, timedelta

from pydantic import ValidationError
import pytest

from daikanban.model import Board, DuplicateProjectNameError, Project, ProjectNotFoundError, Task, TaskNotFoundError, TaskStatus, TaskStatusError
from daikanban.utils import TIME_FORMAT, get_current_time


class TestTask:

    def test_replace(self):
        now = get_current_time()
        task = Task(name='task', created_time=now)
        assert task._replace(name='new').name == 'new'
        assert task._replace(name='new')._replace(name='task') == task
        assert task == Task(name='task', created_time=now)
        with pytest.raises(TypeError, match="Unknown field 'fake'"):
            _ = task._replace(fake='value')
        # types are coerced
        assert isinstance(task._replace(due_date=get_current_time().strftime(TIME_FORMAT)).due_date, datetime)

    def test_valid_name(self):
        _ = Task(name='a')
        _ = Task(name=' .a\n')
        with pytest.raises(ValidationError):
            _ = Task(name='')
        with pytest.raises(ValidationError):
            _ = Task(name='1')
        with pytest.raises(ValidationError):
            _ = Task(name='.')

    def test_valid_duration(self):
        task = Task(name='task', expected_duration=None)
        assert task.expected_duration is None
        task = Task(name='task', expected_duration='1 day')
        assert task.expected_duration == 1
        with pytest.raises(ValidationError, match='Invalid time duration'):
            _ = Task(name='task', expected_duration='1 month')
        with pytest.raises(ValidationError, match='Invalid time duration'):
            _ = Task(name='task', expected_duration='not a time')
        task = Task(name='task', expected_duration='31 days')
        assert task.expected_duration == 31
        task = Task(name='task', expected_duration=50)
        assert task.expected_duration == 50
        with pytest.raises(ValidationError, match='should be greater than or equal to 0'):
            _ = Task(name='task', expected_duration=-1)

    def test_schema(self):
        schema = Task.model_json_schema(mode='serialization')
        # FIXME: computed fields should not be required?
        computed_fields = ['status', 'total_time_worked', 'lead_time', 'is_overdue']
        assert schema['required'] == ['name'] + computed_fields
        for field in computed_fields:
            assert schema['properties'][field]['readOnly'] is True

    def test_status(self):
        todo = Task(name='task')
        assert todo.status == TaskStatus.todo == 'todo'
        assert todo.first_started_time is None
        assert todo.last_paused_time is None
        assert todo.completed_time is None
        with pytest.raises(TaskStatusError, match='cannot complete'):
            _ = todo.completed()
        started = todo.started()
        time_worked = started.total_time_worked
        assert started != todo
        assert started.status == TaskStatus.active
        assert isinstance(started.first_started_time, datetime)
        assert started.last_started_time is None
        assert started.prior_time_worked is None
        assert started.last_paused_time is None
        assert started.completed_time is None
        with pytest.raises(TaskStatusError, match='cannot start'):
            _ = started.started()
        with pytest.raises(TaskStatusError, match='cannot resume'):
            _ = started.resumed()
        # additional time is worked since the task started
        assert started.total_time_worked > time_worked
        paused = started.paused()
        time_worked = paused.total_time_worked
        assert paused.status == TaskStatus.paused
        assert paused.last_started_time is None
        assert isinstance(paused.last_paused_time, datetime)
        assert isinstance(paused.prior_time_worked, float)
        # no additional time is worked since task is paused
        assert paused.total_time_worked == time_worked
        resumed = paused.resumed()
        assert isinstance(resumed.last_started_time, datetime)
        assert resumed.first_started_time < resumed.last_started_time
        assert resumed.last_paused_time is None
        _ = resumed.paused()
        completed = started.completed()
        assert isinstance(completed.completed_time, datetime)
        resumed = completed.resumed()
        assert isinstance(resumed.first_started_time, datetime)
        assert isinstance(resumed.last_started_time, datetime)
        assert resumed.last_paused_time is None
        assert resumed.completed_time is None

    def test_reset(self):
        todo = Task(name='task')
        assert isinstance(todo.created_time, datetime)
        assert todo.reset() == todo
        todo2 = todo.model_copy(update={'logs': []})
        assert todo2 != todo
        assert todo2.reset() == todo
        todo3 = todo.model_copy(update={'due_date': get_current_time()})
        assert todo3.reset() == todo
        started = todo.started()
        assert started.reset() == todo
        assert started.reset().status == TaskStatus.todo
        completed = started.completed()
        assert completed.reset() == todo
        assert completed.reset().status == TaskStatus.todo

    def test_timestamps(self):
        dt = get_current_time()
        # a task started in the future is permitted
        task = Task(name='task', first_started_time=(dt + timedelta(days=90)))
        assert task.total_time_worked < 0
        # task cannot be started before it was created
        with pytest.raises(ValidationError, match='start time cannot precede created time'):
            _ = Task(name='task', created_time=dt, first_started_time=(dt - timedelta(days=90)))
        # due date can be before creation
        task = Task(name='task', due_date=(dt - timedelta(days=90)))
        assert task.is_overdue
        # date parsing is flexible
        for val in [dt, dt.isoformat(), dt.strftime(TIME_FORMAT), '2024-01-01', '1/1/2024', 'Jan 1, 2024', 'Jan 1']:
            task = Task(name='task', created_time=val)
            assert isinstance(task.created_time, datetime)
        # invalid timestamps
        for val in ['abcde', '2024', '2024-01--01', '2024-01-01T00:00:00Z-400']:
            with pytest.raises(ValidationError, match='does not match format'):
                _ = Task(name='task', created_time=val)


class TestBoard:

    def test_serialization(self):
        proj = Project(name='myproj')
        proj_id = 0
        task = Task(name='task')
        task_id = 0
        board = Board(name='myboard', projects={proj_id: proj}, tasks={task_id: task})
        for obj in [proj, task, board]:
            d = obj.model_dump()
            assert type(obj)(**d).model_dump() == d

    def test_project_ids(self):
        board = Board(name='myboard')
        assert board.new_project_id() == 0
        assert board.create_project(Project(name='proj0')) == 0
        assert board.new_project_id() == 1
        board.projects[2] = Project(name='proj2')
        # new ID fills in any gaps
        assert board.new_project_id() == 1
        assert board.create_project(Project(name='proj3')) == 1
        assert board.new_project_id() == 3
        board.projects[100] = Project(name='proj100')
        assert board.new_project_id() == 3

    def test_crud_project(self):
        board = Board(name='myboard')
        with pytest.raises(ProjectNotFoundError):
            _ = board.get_project(0)
        proj = Project(name='myproj')
        assert board.create_project(proj) == 0
        assert 0 in board.projects
        assert board.get_project(0) is proj
        board.update_project(0, name='mynewproj')
        assert board.get_project(0) != proj
        assert board.get_project(0).name == 'mynewproj'
        with pytest.raises(ProjectNotFoundError):
            _ = board.update_project(1, name='proj')
        board.delete_project(0)
        assert len(board.projects) == 0
        with pytest.raises(ProjectNotFoundError):
            board.delete_project(0)
        assert board.create_project(proj) == 0

    def test_add_blocking_task(self):
        board = Board(name='myboard')
        task0 = Task(name='task0')
        task1 = Task(name='task1')
        board.create_task(task0)
        assert task0.blocked_by is None
        with pytest.raises(TaskNotFoundError, match='1'):
            board.add_blocking_task(0, 1)
        with pytest.raises(TaskNotFoundError, match='1'):
            board.add_blocking_task(1, 0)
        board.create_task(task1)
        board.add_blocking_task(0, 1)
        assert task1.blocked_by is None  # no mutation on original task
        assert board.get_task(1).blocked_by == {0}

    def test_duplicate_project_names(self):
        board = Board(name='myboard')
        board.create_project(Project(name='proj0'))
        with pytest.raises(DuplicateProjectNameError, match='Duplicate project name'):
            board.create_project(Project(name='proj0'))
        board.create_project(Project(name='proj1'))
        with pytest.raises(DuplicateProjectNameError, match='Duplicate project name'):
            board.update_project(1, name='proj0')
        board.update_project(0, name='proj2')
        board.update_project(1, name='proj0')
