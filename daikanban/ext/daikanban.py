from typing import IO, Any

from daikanban.ext.export import JSONExporter, JSONWritable
from daikanban.model import Board


class BoardDict(dict[str, Any], JSONWritable):
    """Pass-through object for a Board, conforming to the JSONWritable interface."""

    def to_json_obj(self) -> Any:
        """Returns a dict that can be JSON-serialized."""
        return self

    def write(self, fp: IO[str], **kwargs: Any) -> None:
        """Write to JSON file, making sure datetimes are encoded as ISO strings."""
        super().write(fp, cls=Board.json_encoder(), **kwargs)
        fp.write('\n')


class DaiKanbanExporter(JSONExporter[BoardDict]):
    """Handles exporting to the taskwarrior JSON lines format."""

    def convert_board(self, board: Board) -> BoardDict:
        """Converts the Board to a BoardDict."""
        return BoardDict(board.to_dict())


EXPORTER = DaiKanbanExporter()
