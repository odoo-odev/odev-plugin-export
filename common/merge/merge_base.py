import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from odev.common.logging import logging
from odev.common.version import OdooVersion


logger = logging.getLogger(__name__)


class MergeBase(ABC):
    version: OdooVersion = None
    prettify: bool = False
    xml_ids: list[dict] = None
    migrate_code: bool = True

    def __init__(
        self, version: OdooVersion = None, path: Path = None, prettify: bool = False, migrate_code: bool = True
    ) -> None:
        """Initialize the Merger configuration."""
        self.version: OdooVersion = version
        self.prettify = prettify
        self.path = Path(os.getcwd() if not path else path)
        self.migrate_code = migrate_code

        if not self.path.exists():
            self.path.mkdir(parents=True)

    def merge(self, module: str, code: str, model: str, record: dict, config: dict) -> tuple[Path, str]:
        """Merge the code into the file, check if the file exists and merge the code if it does."""
        file_path, subfolder, file_name = self._get_file_info(config, record)
        module_path = Path(file_path / module / subfolder)

        if not module_path.exists():
            module_path.mkdir(parents=True)

        if Path(module_path / file_name).exists():
            code = self._merge(module_path, file_name, record, code)

        return (Path(module_path / file_name), code if type(code) == str else "\n\n".join(code))

    @abstractmethod
    def _merge(self, file_path: Path, file_name: str, record: dict, code: str):
        raise NotImplementedError("Merge method must be implemented in subclass")

    def _get_file_info(self, config: dict, record: dict) -> tuple[Path, Any, str]:
        record_cp = record.copy()
        file_name = config["file_name_field"]

        for key in file_name.split("-"):
            key = int(key) if type(record_cp) == list else key
            if (type(record_cp) == list and record_cp[key]) or (type(record_cp) == dict and key in record_cp):
                if type(record_cp[key]) in [str, bool, int]:
                    if record_cp[key]:
                        file_name = record_cp[key]
                        break
                else:
                    record_cp = record_cp[key]

        file_name = str(file_name).replace(".", "_").lower()

        return self.path, config["sub_folder"], f"{file_name}.{config['format']}"
