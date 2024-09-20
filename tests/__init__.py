from io import StringIO
from pathlib import Path
import re
from uuid import UUID


TEST_DIR = Path(__file__).parent
TEST_DATA_DIR = TEST_DIR / 'data'


def patch_stdin(monkeypatch, content):
    """Patches stdin with the given input."""
    monkeypatch.setattr('sys.stdin', StringIO(content))

def match_patterns(patterns, string, exact=False):
    """Matches one or more regexes on a string."""
    if patterns is None:
        return
    if not isinstance(patterns, (list, tuple)):
        patterns = [patterns]
    for pattern in patterns:
        if exact:  # exact match
            if isinstance(pattern, str):
                assert pattern == string
            else:
                assert re.compile(pattern).fullmatch(string), f'pattern {pattern.pattern!r} not found'
        else:
            if isinstance(pattern, str):
                pattern = re.compile(pattern, re.DOTALL)
            assert isinstance(pattern, re.Pattern)
            assert pattern.search(string), f'pattern {pattern.pattern!r} not found'

def make_uuid(i: int) -> UUID:
    return UUID('00000000-0000-4000-8000-' + hex(i)[2:].zfill(12))
