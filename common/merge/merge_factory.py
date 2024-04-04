from pathlib import Path

from odev.common.logging import logging

from .merge_base import MergeBase
from .merge_csv import MergeCsv
from .merge_python import MergePython
from .merge_xml import MergeXml


logger = logging.getLogger(__name__)


class MergeFactory(MergeBase):
    def merge(self, module: str, code: str, model: str, record: dict, config: dict) -> tuple[Path, str]:
        if config["format"] == "py":
            return MergePython(self.version, self.path, self.prettify).merge(module, code, model, record, config)
        elif config["format"] == "xml":
            return MergeXml(self.version, self.path, self.prettify).merge(module, code, model, record, config)
        elif config["format"] == "csv":
            return MergeCsv(self.version, self.path, self.prettify).merge(module, code, model, record, config)
        else:
            raise ValueError("Unsupported data type")

    def _merge(self, file_path: Path, file_name: str, record: dict, code: str):
        raise NotImplementedError("Merge method must be implemented in subclass")
