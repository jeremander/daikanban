from abc import ABC, abstractmethod
from collections.abc import Iterable
import json
from pathlib import Path
from typing import IO, Any, ClassVar, Generic, TypeVar, Union

from daikanban.model import Board


T = TypeVar('T')
T_IO = TypeVar('T_IO')

AnyPath = Union[str, Path]


class FileWritable(ABC, Generic[T_IO]):
    """Base class for something that can be serialized to a file."""

    @abstractmethod
    def write(self, fp: T_IO, **kwargs: Any) -> None:
        """Writes to a file-like object."""


FW = TypeVar('FW', bound=FileWritable)


class JSONExportable(ABC):
    """Base class for an object that can be converted to a JSON object."""

    @abstractmethod
    def to_json_obj(self) -> Any:
        """Converts the object to a JSON-serializable object."""


class JSONWritable(JSONExportable, FileWritable[IO[str]]):
    """Base class for something that can write to a JSON file."""

    def write(self, fp: IO[str], **kwargs: Any) -> None:
        """Writes to a JSON file."""
        json.dump(self.to_json_obj(), fp, **kwargs)


class JSONLinesWritable(JSONExportable, FileWritable[IO[str]]):
    """Base class for something that can write to a JSONL (JSON lines) file."""

    def write(self, fp: IO[str], **kwargs: Any) -> None:
        """Writes to a JSON lines file."""
        obj = self.to_json_obj()
        assert isinstance(obj, Iterable)
        for val in obj:
            fp.write(json.dumps(val, indent=None, **kwargs))
            fp.write('\n')


class BaseExporter(ABC, Generic[FW]):
    """Base class for exporting a daikanban Board to some external file format."""
    write_mode: ClassVar[str]  # file write mode

    @abstractmethod
    def convert_board(self, board: Board) -> FW:
        """Converts a Board to the associated type."""

    def write_board(self, board: Board, fp: IO[Any], **kwargs: Any) -> None:
        """Saves a Board to a file-like object."""
        self.convert_board(board).write(fp, **kwargs)

    def export_board(self, board: Board, path: AnyPath, **kwargs: Any) -> None:
        """Saves a Board to a file."""
        with open(path, mode=self.write_mode) as fp:
            self.write_board(board, fp, **kwargs)


J = TypeVar('J', bound=JSONWritable)


class JSONExporter(BaseExporter[J]):
    """Base class for exporting a Board to a JSON file."""
    write_mode = 'w'


class JSONLinesExporter(BaseExporter[J]):
    """Base class for exporting a Board to a JSONL (JSON lines) file."""
    write_mode = 'w'
