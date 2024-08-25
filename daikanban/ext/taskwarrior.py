from datetime import datetime
from typing import IO, Any, Optional

from pydantic.dataclasses import dataclass

from daikanban.io import JSONLinesExporter, JSONLinesWritable
from daikanban.model import Board, Id, Model, ModelJSONEncoder, Task
from daikanban.task import TaskStatus


DATE_FORMAT = '%Y%m%dT%H%M%SZ'


class TaskwarriorJSONEncoder(ModelJSONEncoder):
    """Custom JSONEncoder ensuring that dates are encoded in the proper format."""

    def default(self, obj: Any) -> Any:
        """Encodes an object to JSON."""
        if isinstance(obj, datetime):
            return obj.strftime(DATE_FORMAT)
        return super().default(obj)


@dataclass(frozen=True)
class TwTask(Model):
    """Model class representing a Taskwarrior task."""
    id: int
    description: str
    annotations: Optional[list[str]] = None
    depends: Optional[list[str]] = None
    due: Optional[datetime] = None
    end: Optional[datetime] = None
    entry: Optional[datetime] = None
    imask: Optional[int] = None
    mask: Optional[str] = None
    modified: Optional[datetime] = None
    parent: Optional[str] = None
    project: Optional[str] = None
    recur: Optional[datetime] = None
    scheduled: Optional[datetime] = None
    start: Optional[datetime] = None
    status: Optional[str] = None
    tags: Optional[list[str]] = None
    until: Optional[datetime] = None
    uuid: Optional[str] = None
    wait: Optional[datetime] = None
    udas: Optional[dict[str, Any]] = None

    def to_dict(self, **kwargs: Any) -> dict[str, Any]:
        """Converts a TwTask to a JSON-serializable dict."""
        d = super().to_dict(**kwargs)
        if 'udas' in d:
            del d['udas']
        if self.udas:
            d.update({key: val for (key, val) in self.udas.items() if (key not in d) and (val is not None)})
        return d


class TaskList(list[TwTask], JSONLinesWritable):
    """A list of taskw Tasks that can be serialized to taskwarrior JSON entries."""

    def to_json_obj(self) -> Any:
        """Returns a list of tasks as serializable JSON dicts."""
        return [task.to_dict() for task in self]

    def write(self, fp: IO[str], **kwargs: Any) -> None:
        """Write to JSON file, making sure datetimes are encoded as ISO strings."""
        kwargs = {'cls': TaskwarriorJSONEncoder, 'separators': (',', ':'), **kwargs}
        super().write(fp, **kwargs)


class TaskwarriorExporter(JSONLinesExporter[TaskList]):
    """Handles exporting to the taskwarrior JSON lines format."""

    def convert_task(self, board: Board, id_: Id, task: Task) -> TwTask:
        """Converts a daikanban Task to a taskw Task."""
        extra = task.extra or {}
        project = None if (task.project_id is None) else board.projects[task.project_id].name
        data = {
            'id': id_,
            'annotations': task.notes,
            'description': task.name,
            'due': task.due_time,
            'end': task.completed_time,
            'entry': task.created_time,
            'modified': task.modified_time,
            # taskwarrior does not have project IDs
            # TODO: warn if a name collision occurs
            'project': project,
            'start': task.first_started_time,
            'status': 'completed' if (task.status == TaskStatus.complete) else 'pending',
            'tags': sorted(task.tags) if task.tags else None,
            # TODO: store UUIDs of parent/blocking tasks (not yet supported)
            'depends': extra.get('depends'),
            'parent': extra.get('parent'),
            # the remaining fields are not represented in daikanban
            'imask': extra.get('imask'),
            'mask': extra.get('mask'),
            'recur': extra.get('recur'),
            'scheduled': extra.get('scheduled'),
            'until': extra.get('until'),
            'uuid': extra.get('uuid'),
            'wait': extra.get('wait'),
        }
        # TODO: make UDA names configurable (via command-line or config file)
        udas = {
            'long': task.description,
            'expected_difficulty': task.expected_difficulty,
            'expected_duration': task.expected_duration,
            # this should be a numeric UDA field
            'priority': task.priority,
            'project_id': task.project_id,
            'links': sorted(task.links) if task.links else None,
        }
        udas.update({key: val for (key, val) in extra.items() if (key not in data) and (key not in udas)})
        data['udas'] = udas
        return TwTask(**data)  # type: ignore[arg-type]

    def convert_from_board(self, board: Board) -> TaskList:
        """Converts the tasks in a Board to a list of taskwarrior tasks."""
        tw_tasks = TaskList()
        for id_ in sorted(board.tasks):
            task = board.tasks[id_]
            tw_tasks.append(self.convert_task(board, id_, task))
        return tw_tasks


EXPORTER = TaskwarriorExporter()
