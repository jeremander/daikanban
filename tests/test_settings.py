from datetime import date, datetime

from pydantic import ValidationError
import pytest

from daikanban.score import TASK_SCORERS, TaskScorer
from daikanban.settings import DEFAULT_DATE_FORMAT, DEFAULT_TASK_SCORER_NAME, Settings, TaskSettings
from daikanban.utils import UserInputError, get_current_time


# (time, is_future)
VALID_RELATIVE_TIMES = [
    ('now', False),
    ('in 2 days', True),
    ('in three days', True),
    ('in 0 days', False),
    ('4 weeks ago', False),
    ('five days ago', False),
    ('3 days', True),
    ('3 day', True),
    ('yesterday', False),
    ('today', False),
    ('tomorrow', True),
    ('2 months', True),
    ('in 2 years', True),
    ('2 months ago', False),
    ('2 years ago', False),
]

INVALID_RELATIVE_TIMES = [
    ('invalid time', True),
    ('3', True),
]

@pytest.mark.parametrize(['string', 'is_future', 'valid'], [
    *[(s, is_future, True) for (s, is_future) in VALID_RELATIVE_TIMES],
    *[(s, is_future, False) for (s, is_future) in INVALID_RELATIVE_TIMES]
])
def test_parse_relative_time(string, is_future, valid):
    settings = Settings.global_settings().time
    if valid:
        dt = settings.parse_datetime(string)
    else:
        with pytest.raises(UserInputError, match='Invalid time'):
            _ = settings.parse_datetime(string)
        return
    assert isinstance(dt, datetime)
    now = get_current_time()
    if is_future:
        assert dt > now
    else:
        assert dt < now


def test_global_settings():
    dt = date(2024, 1, 1)
    def _pretty_value(val):
        return Settings.global_settings().pretty_value(val)
    orig_settings = Settings.global_settings()
    assert orig_settings.time.date_format == DEFAULT_DATE_FORMAT
    assert _pretty_value(dt) == dt.strftime(DEFAULT_DATE_FORMAT)
    new_settings = orig_settings.model_copy(deep=True)
    new_date_format = '*%Y-%m-%d*'
    new_settings.time.date_format = new_date_format
    assert _pretty_value(dt) == dt.strftime(DEFAULT_DATE_FORMAT)
    new_settings.update_global_settings()
    assert _pretty_value(dt) == '*2024-01-01*'
    assert _pretty_value(dt) == dt.strftime(new_date_format)
    cur_settings = Settings.global_settings()
    assert cur_settings != orig_settings
    assert cur_settings is new_settings
    assert cur_settings.time.date_format == new_date_format
    # restore original settings
    orig_settings.update_global_settings()
    cur_settings = Settings.global_settings()
    assert cur_settings != new_settings
    assert cur_settings is orig_settings
    assert cur_settings.time.date_format == DEFAULT_DATE_FORMAT
    assert _pretty_value(dt) == dt.strftime(DEFAULT_DATE_FORMAT)

def test_task_scorer():
    settings = Settings.global_settings()
    assert settings.task.scorer_name == DEFAULT_TASK_SCORER_NAME
    assert DEFAULT_TASK_SCORER_NAME in TASK_SCORERS
    assert isinstance(TASK_SCORERS[DEFAULT_TASK_SCORER_NAME], TaskScorer)
    fake_scorer_name = 'fake-scorer'
    assert fake_scorer_name not in TASK_SCORERS
    with pytest.raises(ValidationError, match='Unknown task scorer'):
        _ = TaskSettings(scorer_name=fake_scorer_name)
