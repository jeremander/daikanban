from enum import Enum


class ExportFormat(str, Enum):
    """Enumeration of known BoardExporter export formats."""
    taskwarrior = 'taskwarrior'


EXPORTERS = {}
