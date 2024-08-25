from typing import IO, Any

from daikanban.io import JSONExporter, JSONWritable
from daikanban.model import Board, ModelJSONEncoder


class BoardDict(dict[str, Any], JSONWritable):
    """Pass-through object for a Board, conforming to the JSONWritable interface."""

    def to_json_obj(self) -> Any:
        """Returns a dict that can be JSON-serialized."""
        return self

    def write(self, fp: IO[str], **kwargs: Any) -> None:
        """Write to JSON file, making sure datetimes are encoded as ISO strings."""
        super().write(fp, cls=ModelJSONEncoder, **kwargs)


class DaiKanbanExporter(JSONExporter[BoardDict]):
    """Handles exporting to the taskwarrior JSON lines format."""

    def convert_board(self, board: Board) -> BoardDict:
        """Converts the Board to a BoardDict."""
        return BoardDict(board.to_dict())


EXPORTER = DaiKanbanExporter()
