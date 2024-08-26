from enum import Enum
from importlib import import_module

from daikanban.io import BaseImporter


class ImportFormat(str, Enum):
    """Enumeration of known BoardImporter import formats."""
    daikanban = 'daikanban'
    taskwarrior = 'taskwarrior'

    @property
    def importer(self) -> BaseImporter:
        """Gets the BaseImporter class associated with this format."""
        mod = import_module(f'daikanban.ext.{self.name}')
        return mod.IMPORTER
