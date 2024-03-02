from datetime import datetime

import pytest

from daikanban.model import DaiKanban, Project, ProjectNotFoundError, Task, TaskNotFoundError, TaskStatus, TaskStatusError


class TestTask:

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
        assert todo.completed_time is None
        with pytest.raises(TaskStatusError, match='cannot complete'):
            _ = todo.completed()
        started = todo.started()
        assert started != todo
        assert started.status == TaskStatus.active
        assert isinstance(started.first_started_time, datetime)
        assert started.first_started_time == started.last_started_time
        assert started.prior_time_worked is None
        assert started.completed_time is None
        with pytest.raises(TaskStatusError, match='cannot start'):
            _ = started.started()
        with pytest.raises(TaskStatusError, match='cannot restart'):
            _ = started.restarted()
        paused = started.paused()
        assert paused.status == TaskStatus.paused
        assert paused.last_started_time is None
        assert isinstance(paused.prior_time_worked, float)
        restarted = paused.restarted()
        assert isinstance(restarted.last_started_time, datetime)
        assert restarted.first_started_time < restarted.last_started_time
        _ = restarted.paused()
        completed = started.completed()
        assert isinstance(completed.completed_time, datetime)
        with pytest.raises(TaskStatusError, match='cannot restart'):
            _ = completed.restarted()


class TestDaiKanban:

    def test_serialization(self):
        proj = Project(name='myproj')
        proj_id = 0
        task = Task(name='mytask')
        task_id = 0
        dk = DaiKanban(name='myboard', projects={proj_id: proj}, tasks={task_id: task})
        for obj in [proj, task, dk]:
            d = obj.model_dump()
            assert type(obj)(**d).model_dump() == d

    def test_project_ids(self):
        dk = DaiKanban(name='myboard')
        assert dk.new_project_id() == 0
        assert dk.create_project(Project(name='proj0')) == 0
        assert dk.new_project_id() == 1
        dk.projects[2] = Project(name='proj2')
        assert dk.new_project_id() == 3
        assert dk.create_project(Project(name='proj3')) == 3
        assert dk.new_project_id() == 4

    def test_crud_project(self):
        dk = DaiKanban(name='myboard')
        with pytest.raises(ProjectNotFoundError):
            _ = dk.get_project(0)
        proj = Project(name='myproj')
        assert dk.create_project(proj) == 0
        assert 0 in dk.projects
        assert dk.get_project(0) is proj
        dk.update_project(0, name='mynewproj')
        assert dk.get_project(0) != proj
        assert dk.get_project(0).name == 'mynewproj'
        with pytest.raises(ProjectNotFoundError):
            _ = dk.update_project(1, name='proj')
        dk.delete_project(0)
        assert len(dk.projects) == 0
        with pytest.raises(ProjectNotFoundError):
            dk.delete_project(0)
        assert dk.create_project(proj) == 0

    def test_add_blocking_task(self):
        dk = DaiKanban(name='myboard')
        task0 = Task(name='task0')
        task1 = Task(name='task1')
        dk.create_task(task0)
        assert task0.blocked_by is None
        with pytest.raises(TaskNotFoundError, match='1'):
            dk.add_blocking_task(0, 1)
        with pytest.raises(TaskNotFoundError, match='1'):
            dk.add_blocking_task(1, 0)
        dk.create_task(task1)
        dk.add_blocking_task(0, 1)
        assert task1.blocked_by is None  # no mutation on original task
        assert dk.get_task(1).blocked_by == {0}
