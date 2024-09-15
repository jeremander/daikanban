from copy import deepcopy
from datetime import datetime, timedelta
import uuid

from pydantic import ValidationError
from pydantic_core import Url
import pytest

from daikanban.config import DEFAULT_DATETIME_FORMAT, get_config
from daikanban.model import AmbiguousProjectNameError, AmbiguousTaskNameError, Board, DuplicateProjectError, Project, ProjectNotFoundError, Relation, Task, TaskNotFoundError, TaskStatus, TaskStatusAction, TaskStatusError, UUIDImmutableError, VersionMismatchError, load_board
from daikanban.task import TASK_SCORERS
from daikanban.utils import case_insensitive_match, fuzzy_match, get_current_time


always_match = lambda s1, s2: True


class TestProject:

    def test_links(self):
        proj = Project(name='proj')
        assert proj.links is None
        proj = Project(name='proj', links='')
        assert proj.links == set()
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
        proj = Project(name='proj', links='link1.com')
        assert proj.links == {Url('https://link1.com')}
        proj = Project(name='proj', links='link1.com, link2.org')
        assert proj.links == {Url('https://link1.com'), Url('https://link2.org')}


class TestTask:

    def test_priority(self):
        assert Task(name='task', priority=1).priority == 1
        assert Task(name='task', priority=0).priority == 0
        with pytest.raises(ValidationError, match='Input should be greater than or equal to 0'):
            _ = Task(name='task', priority=-1)
        assert Task(name='task', priority='1').priority == 1
        with pytest.raises(ValidationError, match='Input should be greater than or equal to 0'):
            _ = Task(name='task', priority='-1')
        with pytest.raises(ValidationError, match='Input should be a valid number'):
            _ = Task(name='task', priority='a')
        assert Task(name='task', priority=None).priority is None
        assert Task(name='task').priority is None
        assert Task(name='task', priority='').priority is None

    def test_duration(self):
        assert Task(name='task', expected_duration=5).expected_duration == 5
        with pytest.raises(ValidationError, match='Invalid time duration'):
            _ = Task(name='task', expected_duration='fake duration')
        with pytest.raises(ValidationError, match='Invalid time duration'):
            _ = Task(name='task', expected_duration='5')
        assert Task(name='task', expected_duration='5 days').expected_duration == 5
        assert Task(name='task', expected_duration='1 week').expected_duration == 7
        assert Task(name='task').expected_duration is None
        assert Task(name='task', expected_duration=None).expected_duration is None
        assert Task(name='task', expected_duration='').expected_duration is None

    def test_due_time(self):
        dt = get_config().time.parse_datetime('2024-01-01')
        assert Task(name='task').due_time is None
        assert Task(name='task', due_time=None).due_time is None
        assert Task(name='task', due_time='').due_time is None
        assert Task(name='task', due_time=dt).due_time == dt
        assert Task(name='task', due_time=dt.strftime(DEFAULT_DATETIME_FORMAT)).due_time == dt

    def test_tags(self):
        assert Task(name='task').tags is None
        assert Task(name='task', tags=None).tags is None
        assert Task(name='task', tags={'a', 'b'}).tags == {'a', 'b'}
        assert Task(name='task', tags='').tags == set()
        assert Task(name='task', tags='a').tags == {'a'}
        assert Task(name='task', tags='a,b').tags == {'a', 'b'}
        assert Task(name='task', tags=' a,  b').tags == {'a', 'b'}

    def test_replace(self):
        now = get_current_time()
        u = uuid.uuid4()
        task = Task(name='task', uuid=u, created_time=now, modified_time=now)
        assert task._replace(name='new').name == 'new'
        assert task._replace(name='new')._replace(name='task') == task
        assert task == Task(name='task', uuid=u, created_time=now, modified_time=now)
        with pytest.raises(TypeError, match="Unknown field 'fake'"):
            _ = task._replace(fake='value')
        # types are coerced
        assert isinstance(task._replace(due_time=get_current_time().strftime(get_config().time.datetime_format)).due_time, datetime)
        assert task._replace(priority='').priority is None

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
        task = Task(name='task', expected_duration='1 month')
        assert task.expected_duration == 30
        task = Task(name='task', expected_duration='1 workweek')
        assert task.expected_duration == 5 * 8 / 24
        with pytest.raises(ValidationError, match='Invalid time duration'):
            _ = Task(name='task', expected_duration='not a time')
        task = Task(name='task', expected_duration='31 days')
        assert task.expected_duration == 31
        task = Task(name='task', expected_duration=50)
        assert task.expected_duration == 50
        with pytest.raises(ValidationError, match='should be greater than or equal to 0'):
            _ = Task(name='task', expected_duration=-1)

    def test_schema(self):
        computed_fields = ['status', 'lead_time', 'cycle_time', 'total_time_worked', 'is_overdue']
        assert Task._computed_fields() == computed_fields
        schema = Task.json_schema(mode='serialization')
        # FIXME: computed fields should not be required?
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
        def _reset_task_is_equal(task1, task2):
            return task1.reset().modified(task2.modified_time) == task2
        todo = Task(name='task')
        assert isinstance(todo.created_time, datetime)
        assert _reset_task_is_equal(todo, todo)
        todo2 = todo._replace(logs=[])
        assert todo2 != todo
        assert _reset_task_is_equal(todo2, todo)
        todo3 = todo._replace(due_time=get_current_time())
        assert _reset_task_is_equal(todo3, todo)
        started = todo.started()
        assert _reset_task_is_equal(started, todo)
        assert started.reset().status == TaskStatus.todo
        completed = started.completed()
        assert _reset_task_is_equal(completed, todo)
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
        task = Task(name='task', due_time=(dt - timedelta(days=90)))
        assert task.is_overdue
        # modified time can be before creation
        task = Task(name='task', created_time=(dt + timedelta(days=90)))
        assert task.modified_time < task.created_time
        # date parsing is flexible
        for val in [dt, dt.isoformat(), dt.strftime(get_config().time.datetime_format), '2024-01-01', '1/1/2024', 'Jan 1, 2024', 'Jan 1']:
            task = Task(name='task', created_time=val)
            assert isinstance(task.created_time, datetime)
        # invalid timestamps
        for val in ['abcde', '2024', '2024-01--01', '2024-01-01T00:00:00Z-400']:
            with pytest.raises(ValidationError, match='Invalid time'):
                _ = Task(name='task', created_time=val)

    def test_modified_time(self):
        dt = get_current_time()
        task = Task(name='task')
        board = Board(name='myboard', tasks={0: task})
        mod_dt = task.modified_time
        assert isinstance(mod_dt, datetime)
        assert mod_dt >= dt
        board.reset_task(0)
        task2 = board.get_task(0)
        assert task2.modified_time >= mod_dt
        assert task2.modified_time is not mod_dt
        assert task2.name is task.name
        board.update_task(0, name='task3')
        task3 = board.get_task(0)
        assert task3.modified_time >= task2.modified_time
        assert task3.modified_time is not task.modified_time
        new_time = dt - timedelta(days=90)
        board.update_task(0, modified_time=new_time)
        task4 = board.get_task(0)
        assert task4.modified_time is new_time
        board.apply_status_action(0, TaskStatusAction.start)
        task5 = board.get_task(0)
        assert task5.modified_time >= task3.modified_time

    def test_scorers(self):
        pri = TASK_SCORERS['priority']
        pri_diff = TASK_SCORERS['priority-difficulty']
        pri_rate = TASK_SCORERS['priority-rate']
        # default configs
        task = Task(name='task')
        assert task.priority is None
        assert task.expected_difficulty is None
        assert task.expected_duration is None
        assert pri(task) == 1
        assert pri_diff(task) == 1
        assert pri_rate(task) == 1 / pri_rate.default_duration
        # specify priority only
        task = Task(name='task', priority=100)
        assert pri(task) == 100
        assert pri_diff(task) == 100
        assert pri_rate(task) == 100 / pri_rate.default_duration
        # specify various fields
        task = Task(name='task', priority=100, expected_difficulty=5, expected_duration='1 day')
        assert pri(task) == 100
        assert pri_diff(task) == 20
        assert pri_rate(task) == 100


class TestBoard:

    def test_serialization(self, tmp_path):
        proj = Project(name='myproj')
        proj_id = 0
        task = Task(name='task')
        task_id = 0
        created_time = datetime.strptime('2024-01-01', '%Y-%m-%d')  # NOTE: no timezone
        board = Board(name='myboard', created_time=created_time, projects={proj_id: proj}, tasks={task_id: task})
        for obj in [proj, task, board]:
            d = obj.to_dict()
            assert type(obj)(**d).to_dict() == d
        assert len(board._project_uuid_to_id) == 1
        assert len(board._task_uuid_to_id) == 1
        board_path = tmp_path / 'board.json'
        board.save(board_path)
        assert board_path.exists()
        for loaded_board in [Board.load(board_path), load_board(board_path)]:
            assert loaded_board == board
            assert loaded_board._project_uuid_to_id == board._project_uuid_to_id
            assert loaded_board._task_uuid_to_id == board._task_uuid_to_id

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

    def test_invalid_project_id(self):
        board = Board(name='myboard')
        board.create_project(Project(name='proj'))
        task = Task(name='task', project_id=1)
        with pytest.raises(ProjectNotFoundError, match='Project with id 1 not found'):
            board.create_task(task)
        board.tasks[0] = task
        with pytest.raises(ValidationError, match='Project with id 1 not found'):
            _ = Board(**board.to_dict())
        with pytest.raises(TaskNotFoundError, match='Task with uuid .* not found'):
            board.delete_task(0)
        del board.tasks[0]
        assert board.create_task(Task(name='task', project_id=0)) == 0
        with pytest.raises(ProjectNotFoundError, match='Project with id 1 not found'):
            board.update_task(0, project_id=1)

    def test_project_uuids(self):
        board = Board(name='myboard')
        proj0 = Project(name='proj0')
        proj1 = Project(name='proj1')
        board.create_project(proj0)
        board.create_project(proj1)
        assert set(board._project_uuid_to_id.values()) == {0, 1}
        uuids = set(board._project_uuid_to_id)
        assert len(uuids) == 2
        assert uuids == {proj.uuid for proj in board.projects.values()}
        with pytest.raises(UUIDImmutableError, match="Cannot modify a project's UUID"):
            board.update_project(0, uuid=uuid.uuid4())
        board.delete_project(0)
        assert set(board._project_uuid_to_id) == {proj1.uuid}
        board.create_project(proj0)
        assert uuids == {proj.uuid for proj in board.projects.values()}
        # try to add a duplicate project
        with pytest.raises(DuplicateProjectError, match='Duplicate project UUID'):
            board.create_project(proj0)

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

    def test_clear(self, test_board):
        name = test_board.name
        created_time = test_board.created_time
        test_board.clear()
        assert test_board == Board(name=name, created_time=created_time, projects={}, tasks={})

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

    def test_duplicate_project_names(self, capsys):
        board = Board(name='myboard')
        board.create_project(Project(name='proj0'))
        # duplicate project name permitted
        board.create_project(Project(name='proj0'))
        assert 'Duplicate project name' in capsys.readouterr().err
        board.delete_project(1)
        board.create_project(Project(name='proj1'))
        board.update_project(1, name='proj0')
        assert 'Duplicate project name' in capsys.readouterr().err
        board.update_project(0, name='proj2')
        board.update_project(1, name='proj0')
        assert capsys.readouterr().err == ''

    def test_duplicate_task_names(self, capsys):
        board = Board(name='myboard')
        board.create_task(Task(name='task0'))
        board.create_task(Task(name='task0'))
        assert 'Duplicate task name' in capsys.readouterr().err
        board.delete_task(1)
        # completed tasks do not get counted as duplicate
        board.tasks[0] = board.tasks[0].started().completed()
        board.create_task(Task(name='task0'))
        board = Board(name='myboard')
        board.create_task(Task(name='task0'))
        board.create_task(Task(name='task1'))
        board.update_task(1, name='task0')
        assert 'Duplicate task name' in capsys.readouterr().err
        board.update_task(1, name='task1')
        board.tasks[0] = board.tasks[0].started().completed()
        board.update_task(1, name='task0')
        assert capsys.readouterr().err == ''
        # if a completed task is resumed, check for duplication
        task = board.apply_status_action(0, TaskStatusAction.resume)
        assert 'Duplicate task name' in capsys.readouterr().err
        assert task.status == TaskStatus.active

    def test_name_matching(self):
        config = deepcopy(get_config())._replace(case_sensitive=True)
        with config.as_config():
            board = Board(name='myboard')
            # PROJECT NAMES
            assert board.get_project_id_by_name('abc') is None
            assert board.get_project_id_by_name('abc', always_match) is None
            board.create_project(Project(name='proj0'))
            assert board.get_project_id_by_name('abc') is None
            assert board.get_project_id_by_name('proj0') == 0
            assert board.get_project_id_by_name('abc', always_match) == 0
            assert board.get_project_id_by_name('   proj0', lambda s1, s2: s1.strip() == s2) == 0
            assert board.get_project_id_by_name('PROJ0', case_insensitive_match) == 0
            assert board.get_project_id_by_name('proj', case_insensitive_match) is None
            assert board.get_project_id_by_name('proj', fuzzy_match) == 0
            assert board.get_project_id_by_name('PrO', fuzzy_match) == 0
            assert board.get_project_id_by_name('pr', fuzzy_match) is None
            # multiple projects match case-insensitively
            assert board.create_project(Project(name='PROJ0')) == 1
            assert board.get_project_id_by_name('proj0') == 0
            assert board.get_project_id_by_name('PROJ0') == 1
            assert board.get_project_id_by_name('proj0', case_insensitive_match) == 0
            assert board.get_project_id_by_name('PROJ0', case_insensitive_match) == 1
            assert board.get_project_id_by_name('proj0', fuzzy_match) == 0
            assert board.get_project_id_by_name('PROJ0', fuzzy_match) == 1
            assert board.get_project_id_by_name('proj0', always_match) == 0
            assert board.get_project_id_by_name('Proj0') is None
            with pytest.raises(AmbiguousProjectNameError, match='Ambiguous project name'):
                _ = board.get_project_id_by_name('Proj0', case_insensitive_match)
            with pytest.raises(AmbiguousProjectNameError, match='Ambiguous project name'):
                _ = board.get_project_id_by_name('Pro', fuzzy_match)
            with pytest.raises(AmbiguousProjectNameError, match='Ambiguous project name'):
                # this fails because case matching prefix is not given priority over case insensitive prefix
                _ = board.get_project_id_by_name('pro', fuzzy_match)
            # TASK NAMES
            assert board.get_task_id_by_name('abc') is None
            assert board.get_task_id_by_name('abc', always_match) is None
            board.create_task(Task(name='task0'))
            # single active task
            assert board.get_task_id_by_name('abc') is None
            assert board.get_task_id_by_name('task0') == 0
            assert board.get_task_id_by_name('abc', always_match) == 0
            assert board.get_task_id_by_name('TASK0', case_insensitive_match) == 0
            assert board.get_task_id_by_name('TAS', fuzzy_match) == 0
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
            assert board.get_task_id_by_name('task0', case_insensitive_match) == 2
            assert board.get_task_id_by_name('TASK0', case_insensitive_match) == 3
            assert board.get_task_id_by_name('Task0') is None
            with pytest.raises(AmbiguousTaskNameError, match='Ambiguous task name'):
                _ = board.get_task_id_by_name('Task0', case_insensitive_match)
            assert board.create_task(Task(name='Task0')) == 4
            board.apply_status_action(4, TaskStatusAction.complete)
            assert board.get_task_id_by_name('Task0') == 4
            assert board.get_task_id_by_name('Task0', case_insensitive_match) == 4

    @pytest.mark.parametrize('case_sensitive', [True, False])
    def test_name_duplication(self, capsys, case_sensitive):
        """Tests what happens when we create projects or tasks with duplicate names."""
        config = deepcopy(get_config())._replace(case_sensitive=case_sensitive)
        with config.as_config():
            board = Board(name='myboard')
            board.create_project(Project(name='proj'))
            board.update_project(0, name='proj')  # identity is OK
            board.update_project(0, name='PROJ')
            board.update_project(0, name='proj')
            board.create_task(Task(name='task'))
            # always whitespace-insensitive
            board.create_project(Project(name=' proj'))
            assert 'Duplicate project name' in capsys.readouterr().err
            board.create_task(Task(name=' task'))
            assert 'Duplicate task name' in capsys.readouterr().err
            if case_sensitive:
                id_ = board.create_project(Project(name='PROJ'))
                assert board.get_project(id_).name == 'PROJ'
                assert capsys.readouterr().err == ''
                id_ = board.create_task(Task(name='TASK'))
                assert board.get_task(id_).name == 'TASK'
                assert capsys.readouterr().err == ''
            else:
                board.create_project(Project(name='PROJ'))
                assert 'Duplicate project name' in capsys.readouterr().err
                board.create_task(Task(name='TASK'))
                assert 'Duplicate task name' in capsys.readouterr().err
            board.delete_project(2)
            board.delete_task(2)
            board.create_project(Project(name='proj1'))
            board.create_task(Task(name='task1'))
            board.update_task(0, name='task')
            # always whitespace-insensitive
            board.update_project(1, name=' proj')
            assert 'Duplicate project name' in capsys.readouterr().err
            board.update_task(1, name=' task')
            assert 'Duplicate task name' in capsys.readouterr().err
            if case_sensitive:
                board.update_project(1, name='PROJ')
                assert board.get_project_id_by_name('proj') == 0
                assert board.get_project_id_by_name('PROJ') == 1
                assert board.get_project_id_by_name('proj', case_insensitive_match) == 0
                assert board.get_project_id_by_name('PROJ', case_insensitive_match) == 1
                with pytest.raises(AmbiguousProjectNameError, match="Ambiguous project name 'Proj'"):
                    board.get_project_id_by_name('Proj', case_insensitive_match)
                board.update_task(1, name='TASK')
                assert board.get_task_id_by_name('task') == 0
                assert board.get_task_id_by_name('TASK') == 1
                with pytest.raises(AmbiguousTaskNameError, match="Ambiguous task name 'Task'"):
                    board.get_task_id_by_name('Task', case_insensitive_match)
            else:
                board.update_project(1, name='PROJ')
                assert 'Duplicate project name' in capsys.readouterr().err
                board.update_task(1, name='TASK')
                assert 'Duplicate task name' in capsys.readouterr().err

    def _check_board_projects(self, board, projects):
        assert board.projects == projects
        assert board._project_uuid_to_id == {proj.uuid: i for (i, proj) in projects.items()}

    def _check_board_tasks(self, board, tasks):
        assert board.tasks == tasks
        assert board._task_uuid_to_id == {task.uuid: i for (i, task) in tasks.items()}

    def test_update_board_projects(self):
        """Tests what happens to projects when updating a board with another one."""
        board1 = Board(name='board1')
        proj1_0 = Project(name='proj1_0')
        board1.create_project(proj1_0)
        orig_board1 = deepcopy(board1)
        board2 = Board(name='board2')
        board1.update_with_board(board2)
        assert board1 == orig_board1
        # test version mismatch
        board2.version = board1.version + 1
        with pytest.raises(VersionMismatchError, match=f'Attempted to update version {board1.version} board with version {board2.version} board'):
            board1.update_with_board(board2)
        (board1.version, board2.version) = (board2.version, board1.version)
        board1.update_with_board(board2)
        board1.version = board2.version
        assert board1 == orig_board1
        # let other board have project with non-conflicting ID
        proj2_0 = Project(name='proj2_0')
        board2.create_project(proj2_0)
        proj2_1 = Project(name='proj2_1')
        board2.create_project(proj2_1)
        self._check_board_projects(board2, {0: proj2_0, 1: proj2_1})
        board2.delete_project(0)
        self._check_board_projects(board2, {1: proj2_1})
        board1.update_with_board(board2)
        self._check_board_projects(board1, {0: proj1_0, 1: proj2_1})
        # attempt to update with the same project again (nothing happens)
        board1.update_with_board(board2)
        self._check_board_projects(board1, {0: proj1_0, 1: proj2_1})
        # update some attribute of the identical project (nothing happens since modified timestamp is identical)
        board2.update_project(1, name='proj2_1_mod', modified_time=proj2_1.modified_time)
        board1.update_with_board(board2)
        self._check_board_projects(board1, {0: proj1_0, 1: proj2_1})
        # note: updating a project does not change its UUID
        proj2_1_mod = board2.projects[1]
        assert proj2_1_mod != proj2_1
        assert proj2_1_mod.uuid == proj2_1.uuid
        # change modified timestamp to an earlier time (the updated project is still ignored)
        board2.update_project(1, modified_time=proj2_1.modified_time - timedelta(days=1))
        board1.update_with_board(board2)
        self._check_board_projects(board1, {0: proj1_0, 1: proj2_1})
        # change modified timestamp to a later time (now the updated project gets recognized)
        board2.update_project(1, modified_time=proj2_1.modified_time + timedelta(days=1))
        board1.update_with_board(board2)
        self._check_board_projects(board1, {0: proj1_0, 1: board2.projects[1]})
        board1.update_project(1, name=proj2_1.name, modified_time=proj2_1.modified_time)
        # let other board have project with conflicting ID
        board2.create_project(proj2_0)
        board2.delete_project(1)
        self._check_board_projects(board2, {0: proj2_0})
        board1.update_with_board(board2)
        self._check_board_projects(board1, {0: proj1_0, 1: proj2_1, 2: proj2_0})
        # update with a project containing a parent and relation (the IDs must be mapped)
        board1 = deepcopy(orig_board1)
        rel0 = Relation(type='relation', dest=0)
        rel2 = Relation(type='relation', dest=2)
        board2.create_project(Project(name='proj2_1', parent=0, relations=[rel0, rel2]))
        # parent of 1 is 0 in board2 -> in updated board1, ID 0 becomes 1, ID 1 becomes 2, parent of 2 becomes 1 instead of 0
        # for the relations, dest=0 gets mapped to 1, but dest=2 is an unrecognized ID, so it stays the same
        # TODO: should this be an error instead?
        board1.update_with_board(board2)
        self._check_board_projects(board1, {0: proj1_0, 1: board2.projects[0], 2: board2.projects[1]._replace(parent=1, relations=[rel0._replace(dest=1), rel2])})

    def test_update_board_tasks(self):
        """Tests what happens to tasks when updating a board with another one."""
        board1 = Board(name='board1')
        proj1_0 = Project(name='proj1_0')
        board1.create_project(proj1_0)
        task1_0 = Task(name='task1_0', project_id=0)
        board1.create_task(task1_0)
        board2 = Board(name='board2')
        # let other board have task with conflicting project and task ID
        proj2_0 = Project(name='proj2_0')
        board2.create_project(proj2_0)
        task2_0 = Task(name='task2_0', project_id=0)
        board2.create_task(task2_0)
        self._check_board_tasks(board1, {0: task1_0})
        self._check_board_tasks(board2, {0: task2_0})
        board1.update_with_board(board2)
        task2_0_mod = task2_0._replace(project_id=1)
        self._check_board_projects(board1, {0: proj1_0, 1: proj2_0})
        self._check_board_tasks(board1, {0: task1_0, 1: task2_0_mod})
        # attempt to update with the same board again (nothing happens)
        board1.update_with_board(board2)
        self._check_board_projects(board1, {0: proj1_0, 1: proj2_0})
        self._check_board_tasks(board1, {0: task1_0, 1: task2_0_mod})
        # update some attribute of the identical project (nothing happens since modified timestamp is identical)
        board2.update_task(0, name='task2_0_mod', modified_time=task2_0.modified_time)
        board1.update_with_board(board2)
        self._check_board_projects(board1, {0: proj1_0, 1: proj2_0})
        self._check_board_tasks(board1, {0: task1_0, 1: task2_0_mod})
        # change modified timestamp to an earlier time (the updated task is still ignored)
        board2.update_task(0, modified_time=task2_0.modified_time - timedelta(days=1))
        board1.update_with_board(board2)
        self._check_board_tasks(board1, {0: task1_0, 1: task2_0_mod})
        # change modified timestamp to a later time (now the updated task gets recognized)
        board2.update_task(0, modified_time=task2_0.modified_time + timedelta(days=1))
        board1.update_with_board(board2)
        self._check_board_tasks(board1, {0: task1_0, 1: board2.tasks[0]._replace(project_id=1)})
        # create a new task that is a child of the other
        task2_1 = Task(name='task2_1', parent=0)
        board1.delete_task(1)
        board2.delete_task(0)
        board2.create_task(task2_0)
        board2.create_task(task2_1)
        board1.update_with_board(board2)
        self._check_board_tasks(board1, {0: task1_0, 1: board2.tasks[0]._replace(project_id=1), 2: board2.tasks[1]._replace(parent=1)})
