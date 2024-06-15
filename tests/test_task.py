import pytest

from daikanban.model import Task
from daikanban.task import TASK_SCORERS


def test_scorer_dict():
    """Tests dict-serialization of a TaskScorer object."""
    scorer = TASK_SCORERS['priority']
    d = scorer.to_dict()
    assert d == {'name': 'priority', 'description': 'priority only', 'units': 'pri', 'default_priority': 1.0}

@pytest.mark.parametrize(['name', 'score'], [
    ('priority', 5),
    ('priority-difficulty', 1.0),
    ('priority-rate', 2.0),
])
def test_scorer_call(name, score):
    """Tests that a TaskScorer scores a Task as we expect."""
    scorer = TASK_SCORERS[name]
    task = Task(name='task', priority=5, expected_difficulty=5, expected_duration=2.5)
    assert scorer(task) == score
