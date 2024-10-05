from datetime import datetime, timezone
from pathlib import Path

import pytest

from daikanban.board import Board
from daikanban.config import get_config
from daikanban.model import Project, Task

from . import make_uuid


make_dt = lambda s: datetime.strptime(s + 'Z-0500', '%Y-%m-%dZ%z').astimezone(timezone.utc)

CREATED_TIME = make_dt('2024-01-01')
STARTED_TIME = make_dt('2024-01-02')
COMPLETED_TIME = make_dt('2024-01-03')
DUE_TIME = make_dt('2024-01-04')


@pytest.fixture
def use_regular_print(monkeypatch):
    """Fixture to use the regular print function instead of rich.print."""
    monkeypatch.setattr('daikanban.interface.print', print)
    return None

@pytest.fixture(scope='session', autouse=True)
def _tmp_home_dir(tmp_path_factory):
    """Sets the user's home directory to a temporary path."""
    home_dir = tmp_path_factory.mktemp('home')
    with pytest.MonkeyPatch.context() as ctx:
        ctx.setattr(Path, 'home', lambda: home_dir)
        yield

@pytest.fixture
def set_tmp_board_path(tmpdir, monkeypatch):
    """Fixture to set the board path to a temporary directory in the global configurations."""
    cfg = get_config()
    monkeypatch.setattr(cfg.board, 'board_dir', str(tmpdir))
    return None

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

@pytest.fixture
def populate_board_dir(set_tmp_board_path, test_board):
    """Fixture to populate the board directory with some example board JSON files."""
    board_cfg = get_config().board
    board_dir = board_cfg.board_dir_path
    # save test board as the default board
    test_board.save(board_cfg.default_board_path)
    # save an empty board
    Board(name='empty').save(board_dir / 'empty_board.json')
    # save an empty file as JSON (will error loaded)
    (board_dir / 'empty_file.JSON').touch()
    return None
