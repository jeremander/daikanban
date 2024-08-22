from abc import ABC, abstractmethod
from collections.abc import Iterable
import json
from typing import IO, Any, Generic, TypeVar

from daikanban.task import Task


T = TypeVar('T')
T_IO = TypeVar('T_IO')


JSONDict = dict[str, Any]


class BaseExporter(ABC, Generic[T, T_IO]):
    """Base class for exporting Tasks from daikanban to some file format."""

    @abstractmethod
    def convert_task(self, task: Task) -> T:
        """Converts a Task to the associated type."""

    @abstractmethod
    def save_tasks(self, tasks: Iterable[Task], fp: T_IO, **kwargs: Any) -> None:
        """Saves Tasks to a file-like object."""


class JSONDictExportable(ABC):
    """Base class for an object that can be converted to a JSON dict."""

    @abstractmethod
    def to_json_dict(self) -> JSONDict:
        """Converts the object to a JSON-serializable dict."""


J = TypeVar('J', bound=JSONDictExportable)


class JSONExporter(BaseExporter[J, IO[str]]):
    """Base class for exporting Tasks to JSON."""

    def save_tasks_to_json(self, tasks: Iterable[Task], fp: IO[str], **kwargs: Any) -> None:
        """Saves the tasks to a JSON file (list of dicts)."""
        objs = [self.convert_task(task).to_json_dict() for task in tasks]
        json.dump(objs, fp, **kwargs)

    def save_tasks_to_jsonl(self, tasks: Iterable[Task], fp: IO[str], **kwargs: Any) -> None:
        """Saves the tasks to a JSONL file (newline-separated dicts)."""
        for task in tasks:
            fp.write(json.dumps(self.convert_task(task).to_json_dict(), indent=None, **kwargs))
            fp.write('\n')
