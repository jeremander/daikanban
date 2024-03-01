from daikanban.model import DaiKanban, Project, Task, get_new_id


def test_serialization():
    proj = Project(name='myproj')
    proj_id = get_new_id()
    task = Task(name='mytask')
    task_id = get_new_id()
    dk = DaiKanban(name='myboard', projects={proj_id: proj}, tasks={task_id: task})
    for obj in [proj, task, dk]:
        d = obj.model_dump()
        assert type(obj)(**d).model_dump() == d
