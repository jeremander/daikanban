from datetime import datetime

import pytest

from daikanban.model import Board, Project, Task

from . import make_uuid


CREATED_TIME = datetime.strptime('2024-01-01', '%Y-%m-%d')
STARTED_TIME = datetime.strptime('2024-01-02', '%Y-%m-%d')
COMPLETED_TIME = datetime.strptime('2024-01-03', '%Y-%m-%d')
DUE_TIME = datetime.strptime('2024-01-04', '%Y-%m-%d')


@pytest.fixture(scope='module')
def test_board() -> Board:
    """Fixture returning an example DaiKanban Board."""
    projects = {0: Project(name='myproj', uuid=make_uuid(0), description='My cool project.', created_time=CREATED_TIME, modified_time=CREATED_TIME)}
    tasks = {}
    for i in range(3):
        tasks[i] = Task(
            name=f'task{i}',
            uuid=make_uuid(i),
            description=f'Task {i}',
            priority=i,
            expected_difficulty=i,
            created_time=CREATED_TIME,
            modified_time=CREATED_TIME,
        )
    tasks[2] = tasks[2]._replace(
        project_id=0,
        due_time=DUE_TIME,
        tags=['important'],
        links=['www.example.com'],
        notes=['A note.'],
        extra={'some_string': 'string', 'some_int': 3}
    )
    for i in range(1, 3):
        tasks[i] = tasks[i].started(STARTED_TIME).modified(CREATED_TIME)
    tasks[2] = tasks[2].completed(COMPLETED_TIME).modified(CREATED_TIME)
    return Board(name='myboard', created_time=CREATED_TIME, projects=projects, tasks=tasks)
