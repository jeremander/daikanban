import pytest

from daikanban.utils import convert_number_words_to_digits, human_readable_duration


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

@pytest.mark.parametrize(['days', 'prefer_days', 'output'], [
    (1 / (24 * 3600), None, '1 second'),
    (1 / (24 * 60), None, '1 minute'),
    (1 / 24, None, '1 hour'),
    (0.5, None, '12 hours'),
    (1, None, '1 day'),
    (7, False, '1 week'),
    (7, True, '7 days'),
    (10, False, '1 week 3 days'),
    (10, True, '10 days'),
    (365, False, '52 weeks 1 day'),
    (365, True, '365 days'),
])
def test_human_readable_duration(days, prefer_days, output):
    flags = [False, True] if (prefer_days is None) else [prefer_days]
    for flag in flags:
        assert human_readable_duration(days, prefer_days=flag) == output
