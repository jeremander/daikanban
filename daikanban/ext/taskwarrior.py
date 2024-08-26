from contextlib import suppress
from datetime import datetime
from typing import IO, Any, ClassVar, Optional

from pydantic import AnyUrl
from pydantic.dataclasses import dataclass
from typing_extensions import Self

from daikanban.io import JSONExporter, JSONImporter, JSONReadable, JSONWritable
from daikanban.model import Board, Id, Model, ModelJSONEncoder, Project, Task
from daikanban.task import TaskStatus
from daikanban.utils import IdCollection, get_current_time


AnyDict = dict[str, Any]

DATE_FORMAT = '%Y%m%dT%H%M%SZ'


class TaskwarriorJSONEncoder(ModelJSONEncoder):
    """Custom JSONEncoder ensuring that dates are encoded in the proper format."""

    def default(self, obj: Any) -> Any:
        """Encodes an object to JSON."""
        if isinstance(obj, datetime):
            return obj.strftime(DATE_FORMAT)
        return super().default(obj)


@dataclass(frozen=True)
class TwAnnotation(Model):
    """Model class for a Taskwarrior annotation."""
    description: str
    entry: Optional[datetime] = None


@dataclass(frozen=True)
class TwTask(Model):
    """Model class for a Taskwarrior task."""
    id: int
    description: str
    annotations: Optional[list[TwAnnotation]] = None
    depends: Optional[list[str]] = None
    due: Optional[datetime] = None
    end: Optional[datetime] = None
    entry: Optional[datetime] = None
    imask: Optional[int] = None
    mask: Optional[str] = None
    modified: Optional[datetime] = None
    parent: Optional[str] = None
    project: Optional[str] = None
    recur: Optional[datetime | str] = None
    scheduled: Optional[datetime] = None
    start: Optional[datetime] = None
    status: Optional[str] = None
    tags: Optional[list[str]] = None
    until: Optional[datetime] = None
    uuid: Optional[str] = None
    wait: Optional[datetime] = None
    udas: Optional[dict[str, Any]] = None

    # names of taskwarrior fields not currently stored in Daikanban Tasks
    EXTRA_FIELDS: ClassVar[list[str]] = ['depends', 'parent', 'imask', 'mask', 'recur', 'scheduled', 'until', 'uuid', 'wait']

    @classmethod
    def from_dict(cls, d: AnyDict, **kwargs: Any) -> Self:
        """Converts a JSON-deserialized dict to a TwTask."""
        d2 = {}
        udas = {}
        for (key, val) in d.items():
            with suppress(TypeError, ValueError):
                val = datetime.strptime(val, DATE_FORMAT)
            if key in cls.__dataclass_fields__:
                d2[key] = val
            else:  # treat any unrecognized field as a UDA
                udas[key] = val
        if udas:
            d2['udas'] = udas
        return super().from_dict(d2, **kwargs)

    def to_dict(self, **kwargs: Any) -> dict[str, Any]:
        """Converts a TwTask to a JSON-serializable dict."""
        d = super().to_dict(**kwargs)
        if 'udas' in d:
            del d['udas']
        if self.udas:
            d.update({key: val for (key, val) in self.udas.items() if (key not in d) and (val is not None)})
        return d


class TaskList(list[TwTask], JSONReadable, JSONWritable):
    """A list of TwTasks that can be serialized to a taskwarrior JSON file."""

    @classmethod
    def from_json_obj(cls, obj: Any) -> Self:
        """Converts a list of JSON dicts to a TaskList."""
        return cls([TwTask.from_dict(elt) for elt in obj])

    def to_json_obj(self) -> Any:
        """Returns a list of tasks as serializable JSON dicts."""
        return [task.to_dict() for task in self]

    def write(self, fp: IO[str], **kwargs: Any) -> None:
        """Write to JSON file, making sure datetimes are encoded as ISO strings."""
        kwargs = {'indent': 1, 'cls': TaskwarriorJSONEncoder, **kwargs}
        super().write(fp, **kwargs)


class TaskwarriorImporter(JSONImporter[TaskList]):
    """Handles importing from the taskwarrior JSON format."""
    obj_type = TaskList

    def convert_to_board(self, obj: TaskList) -> Board:
        """Converts the tasks in a TaskList to a Board."""
        proj_id_by_name = {}
        projects: list[Project] = []
        task_by_id = {}
        task_ids = IdCollection()  # collection of task IDs used so far
        for task in obj:
            proj_name = task.project
            if isinstance(proj_name, str):
                if proj_name not in proj_id_by_name:
                    proj_id_by_name[proj_name] = len(projects)
                    projects.append(Project(name=proj_name))
                proj_id = proj_id_by_name[proj_name]
            else:
                proj_id = None
            task_id = task_ids.free_id if (task.id is None) else task.id
            udas = dict(task.udas) if task.udas else {}
            udas.pop('project_id', None)  # for now, ignore a stored project ID
            created_time = task.entry or get_current_time()
            if task.start:
                created_time = min(created_time, task.start)
            dkb_task = Task(
                name=task.description,
                description=udas.pop('long', None),
                priority=udas.pop('priority', None),
                expected_difficulty=udas.pop('expected_difficulty', None),
                expected_duration=udas.pop('expected_duration', None),
                due_time=task.due,
                project_id=proj_id,
                tags=set(task.tags) if task.tags else None,
                links=set(map(AnyUrl, udas.pop('links', []))) or None,
                created_time=created_time,
                modified_time=task.modified or get_current_time(),
                first_started_time=task.start,
                last_started_time=None,
                last_paused_time=task.end if (task.start and (task.status == 'pending')) else None,
                completed_time=task.end if (task.start and (task.status == 'completed')) else None,
                prior_time_worked=None,
                # TODO: identify blocking task IDs
                blocked_by=None,
                # TODO: translate from UUID to task ID
                parent=None,
                logs=None,
                notes=[ann.description for ann in task.annotations] if task.annotations else None,
                extra=udas or None,  # put any unused UDA fields into the extras dict
            )
            task_by_id[task_id] = dkb_task
            task_ids.add(task_id)
        # TODO: let user provide name somehow
        return Board(name='', projects=dict(enumerate(projects)), tasks=task_by_id)


class TaskwarriorExporter(JSONExporter[TaskList]):
    """Handles exporting to the taskwarrior JSON format."""

    def convert_task(self, board: Board, id_: Id, task: Task) -> TwTask:
        """Converts a daikanban Task to a TwTask."""
        extra = task.extra or {}
        project = None if (task.project_id is None) else board.projects[task.project_id].name
        data = {
            'id': id_,
            'annotations': [TwAnnotation(description=note) for note in task.notes] if task.notes else None,
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
            **{field: extra.get(field) for field in TwTask.EXTRA_FIELDS},
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


IMPORTER = TaskwarriorImporter()
EXPORTER = TaskwarriorExporter()
