"""API for importing/exporting between DaiKanban boards and external sources."""

from abc import ABC, abstractmethod
from collections.abc import Iterable
import json
from pathlib import Path
from typing import IO, Any, ClassVar, Generic, Type, TypeVar, Union

from typing_extensions import Self

from daikanban.board import Board


T = TypeVar('T')
T_IO = TypeVar('T_IO')

AnyPath = Union[str, Path]


##########
# IMPORT #
##########

class FileReadable(ABC, Generic[T_IO]):
    """Base class for something that can be deserialized from a file."""

    @classmethod
    @abstractmethod
    def read(cls, fp: T_IO, **kwargs: Any) -> Self:
        """Constructs an object from a file-like object."""


FR = TypeVar('FR', bound=FileReadable)


class BaseImporter(ABC, Generic[FR]):
    """Base class for import a daikanban Board from some external file format."""
    read_mode: ClassVar[str]  # file read mode
    obj_type: ClassVar[Type[FR]]  # type: ignore[misc]  # type of the object to convert from

    @abstractmethod
    def convert_to_board(self, obj: FR) -> Board:
        """Converts an object of the associated type to a Board."""

    def read_board(self, fp: IO[Any], **kwargs: Any) -> Board:
        """Loads a Board from a file-like object."""
        return self.convert_to_board(self.obj_type.read(fp, **kwargs))

    def import_board(self, path: AnyPath, **kwargs: Any) -> Board:
        """Loads a Board from a file."""
        with open(path, mode=self.read_mode) as fp:
            return self.read_board(fp, **kwargs)


##########
# EXPORT #
##########

class FileWritable(ABC, Generic[T_IO]):
    """Base class for something that can be serialized to a file."""

    @abstractmethod
    def write(self, fp: T_IO, **kwargs: Any) -> None:
        """Writes to a file-like object."""


FW = TypeVar('FW', bound=FileWritable)


class BaseExporter(ABC, Generic[FW]):
    """Base class for exporting a daikanban Board to some external file format."""
    write_mode: ClassVar[str]  # file write mode

    @abstractmethod
    def convert_from_board(self, board: Board) -> FW:
        """Converts a Board to the associated type."""

    def write_board(self, board: Board, fp: IO[Any], **kwargs: Any) -> None:
        """Saves a Board to a file-like object."""
        self.convert_from_board(board).write(fp, **kwargs)

    def export_board(self, board: Board, path: AnyPath, **kwargs: Any) -> None:
        """Saves a Board to a file."""
        with open(path, mode=self.write_mode) as fp:
            self.write_board(board, fp, **kwargs)


########
# JSON #
########

class JSONImportable(ABC):
    """Base class for an object that can be converted from a JSON object."""

    @classmethod
    @abstractmethod
    def from_json_obj(cls, obj: Any) -> Self:
        """Constructs the object from a JSON-serializable object."""


class JSONReadable(JSONImportable, FileReadable[IO[str]]):
    """Base class for something that can be read from a JSON file."""

    @classmethod
    def read(cls, fp: IO[str], **kwargs: Any) -> Self:
        """Constructs an object from a JSON file."""
        return cls.from_json_obj(json.load(fp, **kwargs))


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


JR = TypeVar('JR', bound=JSONReadable)
JW = TypeVar('JW', bound=JSONWritable)


class JSONImporter(BaseImporter[JR]):
    """Base class for importing a Board from a JSON file."""
    read_mode = 'r'


class JSONExporter(BaseExporter[JW]):
    """Base class for exporting a Board to a JSON file."""
    write_mode = 'w'


#########
# JSONL #
#########

class JSONLinesReadable(JSONImportable, FileReadable[IO[str]]):
    """Base class for something that can be read from a JSONL (JSON lines) file."""

    @classmethod
    def read(cls, fp: IO[str], **kwargs: Any) -> Self:
        """Constructs an object from a JSON lines file."""
        return cls.from_json_obj([json.loads(line, **kwargs) for line in fp])


class JSONLinesWritable(JSONExportable, FileWritable[IO[str]]):
    """Base class for something that can write to a JSONL (JSON lines) file."""

    def write(self, fp: IO[str], **kwargs: Any) -> None:
        """Writes to a JSON lines file."""
        obj = self.to_json_obj()
        assert isinstance(obj, Iterable)
        for val in obj:
            fp.write(json.dumps(val, indent=None, **kwargs))
            fp.write('\n')


JLR = TypeVar('JLR', bound=JSONLinesReadable)
JLW = TypeVar('JLW', bound=JSONLinesWritable)


class JSONLinesImporter(BaseImporter[JLR]):
    """Base class for importing a Board from a JSONL (JSON lines) file."""
    read_mode  = 'r'


class JSONLinesExporter(BaseExporter[JLW]):
    """Base class for exporting a Board to a JSONL (JSON lines) file."""
    write_mode = 'w'
