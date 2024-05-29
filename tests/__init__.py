from io import StringIO


def patch_stdin(monkeypatch, content):
    monkeypatch.setattr('sys.stdin', StringIO(content))
