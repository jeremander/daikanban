from enum import Enum
from importlib import import_module

from daikanban.ext.export import BaseExporter


class ExportFormat(str, Enum):
    """Enumeration of known BoardExporter export formats."""
    taskwarrior = 'taskwarrior'

    @property
    def exporter(self) -> BaseExporter:
        """Gets the BaseExporter class associated with this format."""
        mod = import_module(f'daikanban.ext.{self.name}')
        return mod.EXPORTER
