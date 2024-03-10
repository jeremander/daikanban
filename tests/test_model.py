from datetime import datetime

from pydantic import ValidationError
import pytest

from daikanban.model import Board, Project, ProjectNotFoundError, Task, TaskNotFoundError, TaskStatus, TaskStatusError


class TestTask:

    def test_valid_name(self):
        _ = Task(name='a')
        _ = Task(name=' .a\n')
        with pytest.raises(ValidationError):
            _ = Task(name='')
        with pytest.raises(ValidationError):
            _ = Task(name='1')
        with pytest.raises(ValidationError):
            _ = Task(name='.')

    def test_schema(self):
        schema = Task.model_json_schema(mode='serialization')
        # FIXME: computed fields should not be required?
        computed_fields = ['status', 'total_time_worked', 'lead_time', 'is_overdue']
        assert schema['required'] == ['name'] + computed_fields
        for field in computed_fields:
            assert schema['properties'][field]['readOnly'] is True

    def test_status(self):
        todo = Task(name='mytask')
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
        with pytest.raises(TaskStatusError, match='cannot resume'):
            _ = completed.resumed()


class TestBoard:

    def test_serialization(self):
        proj = Project(name='myproj')
        proj_id = 0
        task = Task(name='mytask')
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
        assert board.new_project_id() == 3
        assert board.create_project(Project(name='proj3')) == 3
        assert board.new_project_id() == 4

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
