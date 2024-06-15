from copy import deepcopy
from datetime import date, datetime

from pydantic import ValidationError
import pytest

from daikanban.config import DEFAULT_DATE_FORMAT, TaskConfig, TimeConfig, get_config
from daikanban.task import DEFAULT_TASK_SCORER_NAME, TASK_SCORERS, TaskScorer
from daikanban.utils import HOURS_PER_DAY, SECS_PER_DAY, UserInputError, get_current_time


MINS_PER_DAY = 60 * HOURS_PER_DAY


def test_work_time_bounds():
    _ = TimeConfig(hours_per_work_day=0.01)
    _ = TimeConfig(hours_per_work_day=24)
    with pytest.raises(ValidationError, match='Input should be greater than 0'):
        _ = TimeConfig(hours_per_work_day=-1)
    with pytest.raises(ValidationError, match='Input should be greater than 0'):
        _ = TimeConfig(hours_per_work_day=0)
    with pytest.raises(ValidationError, match='Input should be less than or equal to 24'):
        _ = TimeConfig(hours_per_work_day=24.01)
    _ = TimeConfig(days_per_work_week=0.01)
    _ = TimeConfig(days_per_work_week=7)
    with pytest.raises(ValidationError, match='Input should be greater than 0'):
        _ = TimeConfig(days_per_work_week=-1)
    with pytest.raises(ValidationError, match='Input should be greater than 0'):
        _ = TimeConfig(days_per_work_week=0)
    with pytest.raises(ValidationError, match='Input should be less than or equal to 7'):
        _ = TimeConfig(days_per_work_week=7.01)


# (time, is_future)
VALID_RELATIVE_TIMES = [
    ('now', False),
    ('in 2 days', True),
    ('in three days', True),
    ('in 0 days', False),
    ('4 weeks ago', False),
    ('five days ago', False),
    ('2 hrs from now', True),
    ('3 days', True),
    ('3 day', True),
    ('yesterday', False),
    ('today', False),
    ('tomorrow', True),
    ('yesterday 0800', False),
    ('yesterday at 08', False),
    ('yesterday at 8', False),
    ('yesterday at 16', False),
    ('yesterday at 12 PM', False),
    ('today 0000', False),
    ('tomorrow 8', True),
    ('tomorrow at  2359', True),
    ('2 months', True),
    ('in 2 years', True),
    ('2 months ago', False),
    ('2 years ago', False),
    ('in 2 days at 3PM', True),
    ('3 months ago 1700', False),
    ('in 1 yr, 12:00', True),
    ('2 years from now at 8 am', True),
    ('last wed', False),
    ('next Tuesday', True),
    ('next sun, 9', True),
]

INVALID_RELATIVE_TIMES = [
    ('invalid time', True),
    ('3', True),
    ('in 1 year ago', True),
    # ('in 2 mins, 5:00', True),
]

@pytest.mark.parametrize(['string', 'is_future', 'valid'], [
    *[(s, is_future, True) for (s, is_future) in VALID_RELATIVE_TIMES],
    *[(s, is_future, False) for (s, is_future) in INVALID_RELATIVE_TIMES]
])
def test_parse_relative_time(string, is_future, valid):
    config = get_config().time
    if valid:
        dt = config.parse_datetime(string)
    else:
        with pytest.raises(UserInputError, match='Invalid time'):
            _ = config.parse_datetime(string)
        return
    assert isinstance(dt, datetime)
    now = get_current_time()
    if is_future:
        assert dt > now
    else:
        assert dt < now

VALID_DURATIONS = [
    ('1 second', 1 / SECS_PER_DAY),
    ('1 seconds', 1 / SECS_PER_DAY),
    ('1 sec', 1 / SECS_PER_DAY),
    ('1 secs', 1 / SECS_PER_DAY),
    ('1 minute', 1 / MINS_PER_DAY),
    ('1 minutes', 1 / MINS_PER_DAY),
    ('1 min', 1 / MINS_PER_DAY),
    ('3 days', 3),
    ('three days', 3),
    ('0 days', 0),
    ('1 week', 7),
    ('1 weeks', 7),
    ('1 year', 365),
    ('1 years', 365),
    ('1 month', 30),
    ('1 months', 30),
    ('1 workweek', 40 / HOURS_PER_DAY),
    ('2 work week', 80 / HOURS_PER_DAY),
    ('1 work-weeks', 40 / HOURS_PER_DAY),
    ('1 workday', 8 / HOURS_PER_DAY),
    ('3 work days', 1),
    ('1.5 weeks', 10.5),
    ('10.1 years', 3686.5),
]

INVALID_DURATIONS = [
    'invalid duration',
    '3',
    '1 seco',
    '1 minu',
    '1 hou',
    '1 wee',
    'now',
    'tomorrow',
    '1 long workday',
    '-3 days',
    '1.2.3 days',
]

@pytest.mark.parametrize(['string', 'days'], VALID_DURATIONS)
def test_parse_duration_valid(string, days):
    config = get_config().time
    dur = config.parse_duration(string)
    assert isinstance(dur, float)
    assert dur == pytest.approx(days)

@pytest.mark.parametrize('string', INVALID_DURATIONS)
def test_parse_duration_invalid(string):
    config = get_config().time
    with pytest.raises(UserInputError, match='Invalid time duration|Time duration cannot be negative'):
        _ = config.parse_duration(string)

def test_global_config():
    dt = date(2024, 1, 1)
    def _pretty_value(val):
        return get_config().pretty_value(val)
    orig_config = get_config()
    assert orig_config.time.date_format == DEFAULT_DATE_FORMAT
    assert _pretty_value(dt) == dt.strftime(DEFAULT_DATE_FORMAT)
    new_config = deepcopy(orig_config)
    new_date_format = '*%Y-%m-%d*'
    new_config.time.date_format = new_date_format
    assert _pretty_value(dt) == dt.strftime(DEFAULT_DATE_FORMAT)
    with new_config.as_config():
        assert _pretty_value(dt) == '*2024-01-01*'
        assert _pretty_value(dt) == dt.strftime(new_date_format)
        cur_config = get_config()
        assert cur_config != orig_config
        assert cur_config is new_config
        assert cur_config.time.date_format == new_date_format
    # original configs are restored
    cur_config = get_config()
    assert cur_config != new_config
    assert cur_config is orig_config
    assert cur_config.time.date_format == DEFAULT_DATE_FORMAT
    assert _pretty_value(dt) == dt.strftime(DEFAULT_DATE_FORMAT)

def test_task_scorer():
    config = get_config()
    assert config.task.scorer_name == DEFAULT_TASK_SCORER_NAME
    assert DEFAULT_TASK_SCORER_NAME in TASK_SCORERS
    assert isinstance(TASK_SCORERS[DEFAULT_TASK_SCORER_NAME], TaskScorer)
    fake_scorer_name = 'fake-scorer'
    assert fake_scorer_name not in TASK_SCORERS
    with pytest.raises(ValidationError, match='Unknown task scorer'):
        _ = TaskConfig(scorer_name=fake_scorer_name)
