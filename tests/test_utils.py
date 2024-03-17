import pytest

from daikanban.utils import convert_number_words_to_digits


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
