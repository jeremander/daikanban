from datetime import datetime
import itertools
import json
from pathlib import Path
from typing import Any, Counter, Literal, Optional
import uuid

from pydantic import UUID4, Field, ValidationError
from pydantic.dataclasses import dataclass
from rich.markup import escape
from typing_extensions import Self

from daikanban import logger
from daikanban.config import Config, get_config
from daikanban.errors import AmbiguousProjectNameError, AmbiguousTaskNameError, BoardFileError, DuplicateProjectError, DuplicateTaskError, ProjectNotFoundError, TaskNotFoundError, UUIDImmutableError, VersionMismatchError, catch_key_error
from daikanban.model import Id, Model, OptionalDatetime, Project, Task, TaskStatusAction, path_style
from daikanban.utils import NameMatcher, count_fmt, exact_match, first_name_match, get_current_time


#########
# BOARD #
#########

@dataclass
class Board(Model):
    """A DaiKanban board (collection of projects and tasks)."""
    name: str = Field(description='Name of DaiKanban board')
    description: Optional[str] = Field(
        default=None,
        description='Description of the DaiKanban board'
    )
    created_time: OptionalDatetime = Field(
        default_factory=get_current_time,
        description='Time the board was created'
    )
    projects: dict[Id, Project] = Field(
        default_factory=dict,
        description='Mapping from IDs to projects'
    )
    tasks: dict[Id, Task] = Field(
        default_factory=dict,
        description='Mapping from IDs to tasks'
    )
    version: Literal[0] = Field(
        default=0,
        description='Version of the DaiKanban specification',
    )

    def __post_init__(self) -> None:
        # mappings from UUIDs to IDs
        self._project_uuid_to_id = {proj.uuid: id_ for (id_, proj) in self.projects.items()}
        self._task_uuid_to_id = {task.uuid: id_ for (id_, task) in self.tasks.items()}
        self.check_valid_project_ids()
        self.check_valid_task_ids()

    def _check_valid_project(self, project: Project) -> None:
        if (project.parent is not None) and (project.parent not in self.projects):
            raise ProjectNotFoundError(project.parent)

    def check_valid_project_ids(self) -> Self:
        """Checks that project IDs associated with all projects and tasks are in the set of known project IDs."""
        for project in self.projects.values():
            self._check_valid_project(project)
        for task in self.tasks.values():
            if (task.project_id is not None) and (task.project_id not in self.projects):
                raise ProjectNotFoundError(task.project_id)
        return self

    def _check_valid_task(self, task: Task) -> None:
        if (task.parent is not None) and (task.parent not in self.tasks):
            raise TaskNotFoundError(task.parent)
        if task.blocked_by:
            for id_ in task.blocked_by:
                if id_ not in self.tasks:
                    raise TaskNotFoundError(id_)

    def check_valid_task_ids(self) -> Self:
        """Checks that tasks IDs associated with all projects and tasks are in the set of known task IDs."""
        for task in self.tasks.values():
            self._check_valid_task(task)
        return self

    @property
    def num_projects(self) -> int:
        """Gets the number of projects."""
        return len(self.projects)

    @property
    def num_tasks(self) -> int:
        """Gets the number of tasks."""
        return len(self.tasks)

    @property
    def _num_proj_num_task_str(self) -> str:
        """Gets a string indicating the number of projects and tasksthe board has."""
        num_proj_str = count_fmt(self.num_projects, 'project')
        num_task_str = count_fmt(self.num_tasks, 'task')
        return f'{num_proj_str}, {num_task_str}'

    def new_project_id(self) -> Id:
        """Gets an available integer as a project ID."""
        return next(filter(lambda id_: id_ not in self.projects, itertools.count()))

    def new_project_uuid(self) -> UUID4:
        """Gets a unique UUID to be used for a new project."""
        while (uuid_ := uuid.uuid4()) not in self._project_uuid_to_id:
            pass
        return uuid_

    def new_task_id(self) -> Id:
        """Gets an available integer as a task ID."""
        return next(filter(lambda id_: id_ not in self.tasks, itertools.count()))

    def new_task_uuid(self) -> UUID4:
        """Gets a unique UUID to be used for a new task."""
        while (uuid_ := uuid.uuid4()) not in self._task_uuid_to_id:
            pass
        return uuid_

    def create_project(self, project: Project) -> Id:
        """Adds a new project and returns its ID."""
        if project.uuid in self._project_uuid_to_id:
            raise DuplicateProjectError(f'Duplicate project UUID {str(project.uuid)!r}')
        self._check_valid_project(project)
        matcher = get_config().name_matcher
        project_names = (p.name for p in self.projects.values())
        if (duplicate_name := first_name_match(matcher, project.name, project_names)) is not None:
            logger.warning(f'Duplicate project name {duplicate_name!r}')
        id_ = self.new_project_id()
        self.projects[id_] = project
        self._project_uuid_to_id[project.uuid] = id_
        return id_

    @catch_key_error(ProjectNotFoundError)
    def get_project(self, project_id: Id) -> Project:
        """Gets a project with the given ID."""
        return self.projects[project_id]

    @staticmethod
    def _filter_id_matches(pairs: list[tuple[Id, bool]]) -> list[Id]:
        if any(exact for (_, exact) in pairs):
            return [id_ for (id_, exact) in pairs if exact]
        return [id_ for (id_, _) in pairs]

    def get_project_id_by_name(self, name: str, matcher: NameMatcher = exact_match) -> Optional[Id]:
        """Gets the ID of the project with the given name, if it matches; otherwise, None."""
        pairs = [(id_, name == p.name) for (id_, p) in self.projects.items() if matcher(name, p.name)]
        ids = self._filter_id_matches(pairs)  # retain only exact matches, if present
        if ids:
            if len(ids) > 1:
                raise AmbiguousProjectNameError(f'Ambiguous project name {name!r}')
            return ids[0]
        return None

    def update_project(self, project_id: Id, **kwargs: Any) -> None:
        """Updates a project with the given keyword arguments."""
        if 'uuid' in kwargs:
            raise UUIDImmutableError("Cannot modify a project's UUID")
        proj = self.get_project(project_id)
        if 'name' in kwargs:
            matcher = get_config().name_matcher
            project_names = (p.name for (id_, p) in self.projects.items() if (id_ != project_id))
            if (duplicate_name := first_name_match(matcher, kwargs['name'], project_names)) is not None:
                logger.warning(f'Duplicate project name {duplicate_name!r}')
        kwargs = {'modified_time': get_current_time(), **kwargs}
        proj = proj._replace(**kwargs)
        self._check_valid_project(proj)
        self.projects[project_id] = proj

    @catch_key_error(ProjectNotFoundError)
    def delete_project(self, project_id: Id) -> None:
        """Deletes a project with the given ID."""
        del self._project_uuid_to_id[self.projects[project_id].uuid]
        del self.projects[project_id]
        # remove project ID from any tasks that have it
        for (task_id, task) in self.tasks.items():
            if task.project_id == project_id:
                self.tasks[task_id] = task._replace(project_id=None)

    def create_task(self, task: Task) -> Id:
        """Adds a new task and returns its ID."""
        if task.uuid in self._task_uuid_to_id:
            raise DuplicateTaskError(f'Duplicate task UUID {str(task.uuid)!r}')
        self._check_valid_task(task)
        if task.project_id is not None:  # validate project ID
            _ = self.get_project(task.project_id)
        matcher = get_config().name_matcher
        incomplete_task_names = (t.name for t in self.tasks.values() if (t.completed_time is None))
        if (duplicate_name := first_name_match(matcher, task.name, incomplete_task_names)) is not None:
            logger.warning(f'Duplicate task name {duplicate_name!r}')
        id_ = self.new_task_id()
        self.tasks[id_] = task
        self._task_uuid_to_id[task.uuid] = id_
        return id_

    @catch_key_error(TaskNotFoundError)
    def get_task(self, task_id: Id) -> Task:
        """Gets a task with the given ID."""
        return self.tasks[task_id]

    def get_task_id_by_name(self, name: str, matcher: NameMatcher = exact_match) -> Optional[Id]:
        """Gets the ID of the task with the given name, if it matches; otherwise, None.
        There may be multiple tasks with the same name, but at most one can be incomplete.
        Behavior is as follows:
            - If there is an incomplete task, chooses this one
            - If there is a single complete task, chooses this one
            - Otherwise, raises AmbiguousTaskNameError"""
        incomplete_pairs: list[tuple[Id, bool]] = []
        complete_pairs: list[tuple[Id, bool]] = []
        for (id_, t) in self.tasks.items():
            if matcher(name, t.name):
                pairs = incomplete_pairs if (t.completed_time is None) else complete_pairs
                pairs.append((id_, name == t.name))
        incomplete_ids = self._filter_id_matches(incomplete_pairs)
        complete_ids = self._filter_id_matches(complete_pairs)
        def _get_id(ids: list[Id], err: str) -> Id:
            if len(ids) > 1:
                raise AmbiguousTaskNameError(err)
            return ids[0]
        # prioritize exact matches, and incomplete over complete
        incomplete_exact_ids = [id_ for (id_, exact) in incomplete_pairs if exact]
        if incomplete_exact_ids:
            return _get_id(incomplete_exact_ids, f'Ambiguous task name {name!r}')
        if any(exact for (_, exact) in complete_pairs):
            return _get_id(complete_ids, f'Multiple completed tasks match name {name!r}')
        if incomplete_ids:
            return _get_id(incomplete_ids, f'Ambiguous task name {name!r}')
        if complete_ids:
            return _get_id(complete_ids, f'Multiple completed tasks match name {name!r}')
        return None

    def update_task(self, task_id: Id, **kwargs: Any) -> None:
        """Updates a task with the given keyword arguments."""
        if 'uuid' in kwargs:
            raise ValueError("Cannot modify a task's UUID")
        task = self.get_task(task_id)
        incomplete_task_names = (t.name for (id_, t) in self.tasks.items() if (id_ != task_id) and (t.completed_time is None))
        kwargs = {'modified_time': get_current_time(), **kwargs}
        task = task._replace(**kwargs)
        if task.project_id is not None:  # validate project ID
            _ = self.get_project(task.project_id)
        self._check_valid_task(task)
        matcher = get_config().name_matcher
        if (duplicate_name := first_name_match(matcher, task.name, incomplete_task_names)) is not None:
            logger.warning(f'Duplicate task name {duplicate_name!r}')
        self.tasks[task_id] = task

    @catch_key_error(TaskNotFoundError)
    def delete_task(self, task_id: Id) -> None:
        """Deletes a task with the given ID."""
        del self._task_uuid_to_id[self.tasks[task_id].uuid]
        del self.tasks[task_id]

    @catch_key_error(TaskNotFoundError)
    def reset_task(self, task_id: Id) -> None:
        """Resets a task with the given ID to the 'todo' state, regardless of its current state.
        This will preserve the original creation metadata except for timestamps, due time, blocking tasks, and logs."""
        task = self.get_task(task_id)
        self.tasks[task_id] = task.reset()

    def apply_status_action(self, task_id: Id, action: TaskStatusAction, dt: Optional[datetime] = None, first_dt: Optional[datetime] = None) -> Task:
        """Changes a task to a new stage, based on the given action at the given time.
        Returns the new task."""
        task = self.get_task(task_id).apply_status_action(action, dt=dt, first_dt=first_dt)
        incomplete_task_names = {t.name for (id_, t) in self.tasks.items() if (id_ != task_id) and (t.completed_time is None)}
        if task.name in incomplete_task_names:
            logger.warning(f'Duplicate task name {task.name!r}')
        self.tasks[task_id] = task
        return task

    @catch_key_error(TaskNotFoundError)
    def add_blocking_task(self, blocking_task_id: Id, blocked_task_id: Id) -> None:
        """Adds a task ID to the list of blocking tasks for another."""
        _ = self.get_task(blocking_task_id)  # ensure blocking task exists
        blocked_task = self.get_task(blocked_task_id)
        blocked_by = set(blocked_task.blocked_by) if blocked_task.blocked_by else set()
        blocked_by.add(blocking_task_id)
        self.tasks[blocked_task_id] = blocked_task._replace(blocked_by=blocked_by)

    @property
    def num_tasks_by_project(self) -> Counter[Id]:
        """Gets a map from project IDs to the number of tasks associated with it."""
        return Counter(task.project_id for task in self.tasks.values() if task.project_id is not None)

    def update_with_board(self, other: Self) -> None:  # noqa: C901
        """Updates the contents of this board with another board, in-place.
        The basic board metadata (such as name) will remain the same as this board's.
        Exact duplicate projects/tasks will be deduplicated using this board's ID.
        Projects/tasks with the same UUID but different contents will be reconciled, using the given ConflictResolutionMode."""
        if other.version > self.version:  # assume backward (but not forward) compatibility
            raise VersionMismatchError(f'Attempted to update version {self.version} board with version {other.version} board')
        proj_id_map = {}  # map from old project IDs to new IDs
        for (other_id, other_proj) in other.projects.items():
            if other_proj.uuid in self._project_uuid_to_id:
                this_id = self._project_uuid_to_id[other_proj.uuid]
                if this_id != other_id:
                    proj_id_map[other_id] = this_id
                if other_proj != (this_proj := self.projects[this_id]):
                    # reconcile two different projects
                    # TODO: do this based on the ConflictResolutionMode
                    if other_proj.modified_time > this_proj.modified_time:  # replace with new project
                        kwargs = other_proj.to_dict()
                        del kwargs['uuid']
                        self.update_project(this_id, **kwargs)
            else:  # ignore other ID and create a new one
                proj_id_map[other_id] = self.create_project(other_proj)
        task_id_map = {}  # map from old task IDs to new IDs
        for (other_id, other_task) in other.tasks.items():
            if other_task.uuid in self._task_uuid_to_id:
                this_id = self._task_uuid_to_id[other_task.uuid]
                if this_id != other_id:
                    task_id_map[other_id] = this_id
                if other_task != (this_task := self.tasks[this_id]):
                    # reconcile two different tasks
                    # TODO: do this based on the ConflictResolutionMode
                    if other_task.modified_time > this_task.modified_time:  # replace with new task
                        kwargs = other_task.to_dict()
                        del kwargs['uuid']
                        self.update_task(this_id, **kwargs)
            else:
                task_id_map[other_id] = self.create_task(other_task)
        # for projects, map foreign project IDs to the new ones
        for proj_id in proj_id_map.values():
            self.projects[proj_id] = self.projects[proj_id]._map_project_ids(proj_id_map)
        # for tasks, map foreign project/task IDs to the new ones
        for task_id in task_id_map.values():
            self.tasks[task_id] = self.tasks[task_id]._map_project_ids(proj_id_map)._map_task_ids(task_id_map)

    def clear(self) -> None:
        """Deletes all projects and tasks."""
        self.projects.clear()
        self.tasks.clear()


def load_board(name_or_path: str | Path, config: Optional[Config] = None) -> Board:
    """Given a board name or path, loads the board from a JSON file."""
    config = config or get_config()
    path = config.resolve_board_name_or_path(name_or_path)
    if not path.exists():
        raise BoardFileError(f'Board file {path_style(path)} does not exist')
    try:
        return Board.load(path)
    except (json.JSONDecodeError, OSError, ValidationError) as e:
        e_str = escape(str(e)) if isinstance(e, ValidationError) else str(e)
        msg = f'When loading JSON {path_style(path)}: {e_str}'
        raise BoardFileError(msg) from None
