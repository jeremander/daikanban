from datetime import datetime

import pytest

from daikanban.utils import UserInputError, convert_number_words_to_digits, get_current_time, parse_date


@pytest.mark.parametrize(['string', 'output'], [
    ('abc', 'abc'),
    ('1 day', '1 day'),
    ('one day', '1 day'),
    ('  one day', '  1 day'),
    ('tone day', 'tone day'),
    ('zero day', '0 day'),
    ('zeroday', 'zeroday')
])
def test_number_words_to_digits(string, output):
    assert convert_number_words_to_digits(string) == output


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
    if valid:
        dt = parse_date(string)
    else:
        with pytest.raises(UserInputError, match='Invalid date'):
            _ = parse_date(string)
        return
    assert isinstance(dt, datetime)
    now = get_current_time()
    if is_future:
        assert dt > now
    else:
        assert dt < now
