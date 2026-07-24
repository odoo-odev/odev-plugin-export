from collections.abc import Generator
from typing import Any

from odev.common.logging import logging

from .converter_base import ConverterBase
from .converter_csv import ConverterCsv
from .converter_python import ConverterPython
from .converter_xml import ConverterXml


logger = logging.getLogger(__name__)

ConverterType = type[ConverterPython | ConverterXml | ConverterCsv]


class ConverterFactory(ConverterBase):
    def convert(
        self, data, fields_get, default_get, model, module: str, config
    ) -> Generator[tuple[dict[Any, Any], str | tuple[str, Any, str, str]], None, None]:
        converter_cls: ConverterType = None

        match config["format"]:
            case "py":
                converter_cls = ConverterPython
            case "xml":
                converter_cls = ConverterXml
            case "csv":
                converter_cls = ConverterCsv
            case _:
                raise ValueError("Unsupported data type")

        return converter_cls(self.version, self.prettify, self.xml_ids, self.migrate_code).convert(
            data, fields_get, default_get, model, module, config
        )
