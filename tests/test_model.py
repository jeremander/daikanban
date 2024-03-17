from datetime import date, datetime, timedelta

from pydantic import ValidationError
from pydantic_core import Url
import pytest

from daikanban.model import AmbiguousProjectNameError, AmbiguousTaskNameError, Board, DuplicateProjectNameError, DuplicateTaskNameError, Project, ProjectNotFoundError, Task, TaskNotFoundError, TaskStatus, TaskStatusAction, TaskStatusError, pretty_value
from daikanban.score import TASK_SCORERS, TaskScorer
from daikanban.settings import DEFAULT_DATE_FORMAT, DEFAULT_TASK_SCORER_NAME, Settings, TaskSettings
from daikanban.utils import fuzzy_match_names, get_current_time


class TestSettings:

    def test_global_settings(self):
        dt = date(2024, 1, 1)
        orig_settings = Settings.global_settings()
        assert orig_settings.time.date_format == DEFAULT_DATE_FORMAT
        assert pretty_value(dt) == dt.strftime(DEFAULT_DATE_FORMAT)
        new_settings = orig_settings.model_copy(deep=True)
        new_date_format = '*%Y-%m-%d*'
        new_settings.time.date_format = new_date_format
        assert pretty_value(dt) == dt.strftime(DEFAULT_DATE_FORMAT)
        new_settings.update_global_settings()
        assert pretty_value(dt) == '*2024-01-01*'
        assert pretty_value(dt) == dt.strftime(new_date_format)
        cur_settings = Settings.global_settings()
        assert cur_settings != orig_settings
        assert cur_settings is new_settings
        assert cur_settings.time.date_format == new_date_format
        # restore original settings
        orig_settings.update_global_settings()
        cur_settings = Settings.global_settings()
        assert cur_settings != new_settings
        assert cur_settings is orig_settings
        assert cur_settings.time.date_format == DEFAULT_DATE_FORMAT
        assert pretty_value(dt) == dt.strftime(DEFAULT_DATE_FORMAT)

    def test_task_scorer(self):
        settings = Settings.global_settings()
        assert settings.task.scorer_name == DEFAULT_TASK_SCORER_NAME
        assert DEFAULT_TASK_SCORER_NAME in TASK_SCORERS
        assert isinstance(TASK_SCORERS[DEFAULT_TASK_SCORER_NAME], TaskScorer)
        fake_scorer_name = 'fake-scorer'
        assert fake_scorer_name not in TASK_SCORERS
        with pytest.raises(ValidationError, match='Unknown task scorer'):
            _ = TaskSettings(scorer_name=fake_scorer_name)


class TestProject:

    def test_links(self):
        proj = Project(name='proj')
        assert proj.links is None
        with pytest.raises(ValidationError, match='Input should be a valid set'):
            proj = Project(name='proj', links='')
        proj = Project(name='proj', links=set())
        assert proj.links == set()
        with pytest.raises(ValidationError, match='Invalid URL'):
            proj = Project(name='proj', links={''})
        with pytest.raises(ValidationError, match='Invalid URL'):
            proj = Project(name='proj', links={'example'})
        proj = Project(name='proj', links={'example.com'})
        assert proj.links == {Url('https://example.com/')}
        proj = Project(name='proj', links={'www.example.com'})
        assert proj.links == {Url('https://www.example.com/')}
        proj = Project(name='proj', links={'http://example.com'})
        assert proj.links == {Url('http://example.com/')}
        proj = Project(name='proj', links={'fake://example.com'})
        assert proj.links == {Url('fake://example.com')}
        proj = Project(name='proj', links={'scheme://netloc/path;parameters?query#fragment'})
        assert proj.links == {Url('scheme://netloc/path;parameters?query#fragment')}


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
        assert isinstance(task._replace(due_date=get_current_time().strftime(Settings.global_settings().time.datetime_format)).due_date, datetime)

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
        computed_fields = ['status', 'lead_time', 'cycle_time', 'total_time_worked', 'is_overdue']
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
        for val in [dt, dt.isoformat(), dt.strftime(Settings.global_settings().time.datetime_format), '2024-01-01', '1/1/2024', 'Jan 1, 2024', 'Jan 1']:
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

    def test_delete_project(self):
        board = Board(name='myboard')
        board.create_project(Project(name='myproj'))
        board.create_task(Task(name='task0', project_id=0))
        board.create_task(Task(name='task1', project_id=0))
        board.delete_project(0)
        assert len(board.projects) == 0
        assert all(task.project_id is None for task in board.tasks.values())

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

    def test_duplicate_task_names(self):
        board = Board(name='myboard')
        board.create_task(Task(name='task0'))
        with pytest.raises(DuplicateTaskNameError, match='Duplicate task name'):
            board.create_task(Task(name='task0'))
        # completed tasks do not get counted as duplicate
        board.tasks[0] = board.tasks[0].started().completed()
        board.create_task(Task(name='task0'))
        board = Board(name='myboard')
        board.create_task(Task(name='task0'))
        board.create_task(Task(name='task1'))
        with pytest.raises(DuplicateTaskNameError, match='Duplicate task name'):
            board.update_task(1, name='task0')
        board.tasks[0] = board.tasks[0].started().completed()
        board.update_task(1, name='task0')
        # if a completed task is resumed, check for duplication
        with pytest.raises(DuplicateTaskNameError, match='Duplicate task name'):
            board.apply_status_action(0, TaskStatusAction.resume)
        board.delete_task(1)
        task = board.apply_status_action(0, TaskStatusAction.resume)
        assert task.status == TaskStatus.active

    def test_name_matching(self):
        always_match = lambda s1, s2: True
        case_insensitive = lambda s1, s2: s1.lower() == s2.lower()
        board = Board(name='myboard')
        # PROJECT NAMES
        assert board.get_project_id_by_name('abc') is None
        assert board.get_project_id_by_name('abc', always_match) is None
        board.create_project(Project(name='proj0'))
        assert board.get_project_id_by_name('abc') is None
        assert board.get_project_id_by_name('proj0') == 0
        assert board.get_project_id_by_name('abc', always_match) == 0
        assert board.get_project_id_by_name('   proj0', lambda s1, s2: s1.strip() == s2) == 0
        assert board.get_project_id_by_name('PROJ0', case_insensitive) == 0
        assert board.get_project_id_by_name('proj', case_insensitive) is None
        assert board.get_project_id_by_name('proj', fuzzy_match_names) == 0
        assert board.get_project_id_by_name('PrO', fuzzy_match_names) == 0
        assert board.get_project_id_by_name('pr', fuzzy_match_names) is None
        # multiple projects match case-insensitively
        assert board.create_project(Project(name='PROJ0')) == 1
        assert board.get_project_id_by_name('proj0') == 0
        assert board.get_project_id_by_name('PROJ0') == 1
        assert board.get_project_id_by_name('proj0', case_insensitive) == 0
        assert board.get_project_id_by_name('PROJ0', case_insensitive) == 1
        assert board.get_project_id_by_name('proj0', fuzzy_match_names) == 0
        assert board.get_project_id_by_name('PROJ0', fuzzy_match_names) == 1
        assert board.get_project_id_by_name('proj0', always_match) == 0
        assert board.get_project_id_by_name('Proj0') is None
        with pytest.raises(AmbiguousProjectNameError, match='Ambiguous project name'):
            _ = board.get_project_id_by_name('Proj0', case_insensitive)
        with pytest.raises(AmbiguousProjectNameError, match='Ambiguous project name'):
            _ = board.get_project_id_by_name('Pro', fuzzy_match_names)
        with pytest.raises(AmbiguousProjectNameError, match='Ambiguous project name'):
            # this fails because case matching prefix is not given priority over case insensitive prefix
            _ = board.get_project_id_by_name('pro', fuzzy_match_names)
        # TASK NAMES
        assert board.get_task_id_by_name('abc') is None
        assert board.get_task_id_by_name('abc', always_match) is None
        board.create_task(Task(name='task0'))
        # single active task
        assert board.get_task_id_by_name('abc') is None
        assert board.get_task_id_by_name('task0') == 0
        assert board.get_task_id_by_name('abc', always_match) == 0
        assert board.get_task_id_by_name('TASK0', case_insensitive) == 0
        assert board.get_task_id_by_name('TAS', fuzzy_match_names) == 0
        # completed task with duplicate name
        task = board.apply_status_action(0, TaskStatusAction.complete)
        assert task.status == TaskStatus.complete
        assert board.get_task_id_by_name('task0') == 0  # completed task the only one
        assert board.create_task(Task(name='task0')) == 1
        assert board.get_task_id_by_name('task0') == 1  # active task chosen, of the two
        task = board.apply_status_action(1, TaskStatusAction.complete)
        assert task.status == TaskStatus.complete
        with pytest.raises(AmbiguousTaskNameError, match='Multiple completed tasks'):
            _ = board.get_task_id_by_name('task0')
        assert board.create_task(Task(name='task0')) == 2
        assert board.get_task_id_by_name('task0') == 2  # active task chosen, of the three
        # multiple tasks match case-insensitively
        assert board.create_task(Task(name='TASK0')) == 3
        assert board.get_task_id_by_name('task0') == 2
        assert board.get_task_id_by_name('TASK0') == 3
        assert board.get_task_id_by_name('task0', case_insensitive) == 2
        assert board.get_task_id_by_name('TASK0', case_insensitive) == 3
        assert board.get_task_id_by_name('Task0') is None
        with pytest.raises(AmbiguousTaskNameError, match='Ambiguous task name'):
            _ = board.get_task_id_by_name('Task0', case_insensitive)
        assert board.create_task(Task(name='Task0')) == 4
        board.apply_status_action(4, TaskStatusAction.complete)
        assert board.get_task_id_by_name('Task0') == 4
        assert board.get_task_id_by_name('Task0', case_insensitive) == 4
