import pytest

from daikanban.prompt import simple_input, validated_input

from . import patch_stdin


@pytest.mark.parametrize(['user_input', 'default', 'match', 'iters', 'value'], [
    ('A', None, '.*', 1, 'A'),
    ('A', None, 'A', 1, 'A'),
    ('B\nA', None, 'A', 2, 'A'),
    ('\n', 'A', '.*', 1, 'A'),
])
def test_simple_input(capsys, monkeypatch, user_input, default, match, iters, value):
    patch_stdin(monkeypatch, user_input)
    assert simple_input('Q', default=default, match=match) == value
    prompt = 'Q'
    if default is not None:
        prompt += f' ({default})'
    prompt += ': '
    assert capsys.readouterr().out == prompt * iters

@pytest.mark.parametrize(['user_input', 'validator', 'default', 'value'], [
    ('A', lambda s: s, None, 'A'),
    ('A', str.lower, None, 'a'),
    ('1', int, None, 1),
    ('A\n1', int, None, 1),
    ('\n', int, 1, 1),
])
def test_validated_input_ok(capsys, monkeypatch, user_input, validator, default, value):
    patch_stdin(monkeypatch, user_input)
    assert validated_input('Q', validator, default=default) == value
