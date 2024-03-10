from datetime import datetime

import pytest

from daikanban.utils import convert_number_words_to_digits, get_current_time, parse_date


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


@pytest.mark.parametrize(['string', 'is_future'], [
    # valid input
    ('now', False),
    ('in 2 days', True),
    ('in three days', True),
    ('in 0 days', False),
    ('4 weeks ago', False),
    ('five days ago', False),
    ('3 days', True),
    # TODO: widen parser's flexibility to cover these cases
    # ('tomorrow', True),
    # ('yesterday', False),
    # ('2 months', True),
    # ('2 years', True),
    # invalid input
    pytest.param('invalid time', True, marks=pytest.mark.xfail),
    pytest.param('3', True, marks=pytest.mark.xfail),
])
def test_parse_relative_time(string, is_future):
    dt = parse_date(string)
    assert isinstance(dt, datetime)
    now = get_current_time()
    if is_future:
        assert dt > now
    else:
        assert dt < now
