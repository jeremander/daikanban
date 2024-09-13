from datetime import datetime
import operator

from daikanban.cli.exporter import ExportFormat
from daikanban.cli.importer import ImportFormat

from . import TEST_DATA_DIR, make_uuid


CREATED_TIME = datetime.strptime('2024-01-01', '%Y-%m-%d')
STARTED_TIME = datetime.strptime('2024-01-02', '%Y-%m-%d')
COMPLETED_TIME = datetime.strptime('2024-01-03', '%Y-%m-%d')
DUE_TIME = datetime.strptime('2024-01-04', '%Y-%m-%d')


class TestImportExport:

    def _test_export_matches_expected(self, test_board, tmp_path, exporter, filename):
        test_path = TEST_DATA_DIR / filename
        export_path = tmp_path / filename
        exporter.export_board(test_board, export_path)
        assert test_path.read_bytes() == export_path.read_bytes()

    def _test_import_is_faithful(self, test_board, importer, filename, eq=None):
        test_path = TEST_DATA_DIR / filename
        board = importer.import_board(test_path)
        eq = operator.eq if (eq is None) else eq
        assert eq(board, test_board)
        assert board is not test_board

    def test_export_daikanban(self, test_board, tmp_path):
        filename = 'daikanban.export.json'
        self._test_export_matches_expected(test_board, tmp_path, ExportFormat.daikanban.exporter, filename)
        # output JSON is just the serialized board
        assert (TEST_DATA_DIR / filename).read_text() == test_board.to_json_string()
        self._test_import_is_faithful(test_board, ImportFormat.daikanban.importer, filename)

    def test_export_taskwarrior(self, test_board, tmp_path):
        filename = 'taskwarrior.export.json'
        self._test_export_matches_expected(test_board, tmp_path, ExportFormat.taskwarrior.exporter, filename)
        def eq(board1, board2):
            # cannot store the name faithfully in taskwarrior JSON
            # TODO: provide user kwargs for setting certain attributes
            kwargs = {'name': '', 'created_time': None}
            # cannot store project metadata faithfully
            proj_kwargs = {'uuid': make_uuid(0), 'description': None, 'created_time': test_board.created_time, 'modified_time': test_board.created_time}
            kwargs1 = {**kwargs, 'projects': {id_: proj._replace(**proj_kwargs) for (id_, proj) in board1.projects.items()}}
            kwargs2 = {**kwargs, 'projects': {id_: proj._replace(**proj_kwargs) for (id_, proj) in board2.projects.items()}}
            return board1._replace(**kwargs1) == board2._replace(**kwargs2)
        self._test_import_is_faithful(test_board, ImportFormat.taskwarrior.importer, filename, eq=eq)
