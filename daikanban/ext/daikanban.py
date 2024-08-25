from typing import IO, Any

from typing_extensions import Self

from daikanban.io import JSONExporter, JSONImporter, JSONReadable, JSONWritable
from daikanban.model import Board, ModelJSONEncoder


class BoardDict(dict[str, Any], JSONReadable, JSONWritable):
    """Pass-through object for a Board, conforming to the JSONReadable and JSONWritable interfaces."""

    @classmethod
    def from_json_obj(cls, obj: Any) -> Self:
        """Converts a JSON-deserialized dict to a BoardDict."""
        return cls(obj)

    def to_json_obj(self) -> Any:
        """Returns a dict that can be JSON-serialized."""
        return self

    def write(self, fp: IO[str], **kwargs: Any) -> None:
        """Write to JSON file, making sure datetimes are encoded as ISO strings."""
        super().write(fp, cls=ModelJSONEncoder, **kwargs)


class DaiKanbanImporter(JSONImporter[BoardDict]):
    """Handles importing a DaiKanban board from a JSON file."""
    obj_type = BoardDict

    def convert_to_board(self, obj: BoardDict) -> Board:
        """Converts a BoardDict to a Board."""
        return Board.from_dict(obj)


class DaiKanbanExporter(JSONExporter[BoardDict]):
    """Handles exporting a DaiKanban board to a JSON file."""

    def convert_from_board(self, board: Board) -> BoardDict:
        """Converts a Board to a BoardDict."""
        return BoardDict(board.to_dict())


IMPORTER = DaiKanbanImporter()
EXPORTER = DaiKanbanExporter()
