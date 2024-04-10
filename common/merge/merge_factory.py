from pathlib import Path
from typing import Type, Union

from odev.common.logging import logging

from .merge_base import MergeBase
from .merge_csv import MergeCsv
from .merge_python import MergePython
from .merge_xml import MergeXml


logger = logging.getLogger(__name__)

MergeType = Type[Union[MergePython, MergeXml, MergeCsv]]


class MergeFactory(MergeBase):
    def merge(self, module: str, code: str, model: str, record: dict, config: dict) -> tuple[Path, str]:
        merge_cls: MergeType = None

        match config["format"]:
            case "py":
                merge_cls = MergePython
            case "xml":
                merge_cls = MergeXml
            case "csv":
                merge_cls = MergeCsv
            case _:
                raise ValueError("Unsupported data type")

        return merge_cls(self.version, self.path, self.prettify).merge(module, code, model, record, config)

    def _merge(self, file_path: Path, file_name: str, record: dict, code: str):
        raise NotImplementedError("Merge method must be implemented in subclass")
