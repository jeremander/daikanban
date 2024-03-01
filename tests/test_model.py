from daikanban.model import DaiKanban, Project, Task


def test_serialization():
    proj = Project(name='myproj')
    proj_id = 0
    task = Task(name='mytask')
    task_id = 0
    dk = DaiKanban(name='myboard', projects={proj_id: proj}, tasks={task_id: task})
    for obj in [proj, task, dk]:
        d = obj.model_dump()
        assert type(obj)(**d).model_dump() == d

def test_project_ids():
    dk = DaiKanban(name='myboard')
    assert dk.new_project_id() == 0
    assert dk.create_project(Project(name='proj0')) == 0
    assert dk.new_project_id() == 1
    dk.projects[2] = Project(name='proj2')
    assert dk.new_project_id() == 3
    assert dk.create_project(Project(name='proj3')) == 3
    assert dk.new_project_id() == 4
