from datetime import datetime

import pytest

from daikanban.cli.exporters import ExportFormat
from daikanban.cli.importers import ImportFormat
from daikanban.model import Board, Project, Task

from . import TEST_DATA_DIR


CREATED_TIME = datetime.strptime('2024-01-01', '%Y-%m-%d')
STARTED_TIME = datetime.strptime('2024-01-02', '%Y-%m-%d')
COMPLETED_TIME = datetime.strptime('2024-01-03', '%Y-%m-%d')
DUE_TIME = datetime.strptime('2024-01-04', '%Y-%m-%d')


@pytest.fixture(scope='module')
def test_board():
    projects = {0: Project(name='myproj', description='My cool project.', created_time=CREATED_TIME, modified_time=CREATED_TIME)}
    tasks = {}
    for i in range(3):
        tasks[i] = Task(
            name=f'task{i}',
            description=f'Task {i}',
            priority=i,
            expected_difficulty=i,
            created_time=CREATED_TIME,
            modified_time=CREATED_TIME
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
        tasks[i] = tasks[i].started(STARTED_TIME)
    tasks[2] = tasks[2].completed(COMPLETED_TIME)
    return Board(name='myboard', created_time=CREATED_TIME, projects=projects, tasks=tasks)


class TestImportExport:

    def _test_export_matches_expected(self, test_board, tmp_path, exporter, filename):
        test_path = TEST_DATA_DIR / filename
        export_path = tmp_path / filename
        exporter.export_board(test_board, export_path)
        assert test_path.read_bytes() == export_path.read_bytes()

    def _test_import_is_faithful(self, test_board, importer, filename):
        test_path = TEST_DATA_DIR / filename
        board = importer.import_board(test_path)
        assert board == test_board
        assert board is not test_board

    def test_export_daikanban(self, test_board, tmp_path):
        filename = 'daikanban.export.json'
        self._test_export_matches_expected(test_board, tmp_path, ExportFormat.daikanban.exporter, filename)
        # output JSON is just the serialized board
        assert (TEST_DATA_DIR / filename).read_text() == test_board.to_json_string()
        self._test_import_is_faithful(test_board, ImportFormat.daikanban.importer, filename)

    def test_export_taskwarrior(self, test_board, tmp_path):
        self._test_export_matches_expected(test_board, tmp_path, ExportFormat.taskwarrior.exporter, 'taskwarrior.export.jsonl')
