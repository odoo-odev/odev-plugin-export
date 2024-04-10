from abc import ABC, abstractmethod
from typing import Any, Generator, Union

from odev.common.connectors.rpc import FieldsGetMapping
from odev.common.logging import logging
from odev.common.version import OdooVersion

from odev.plugins.ps_tech_odev_export.common.odoo import rename_field_base


logger = logging.getLogger(__name__)


class ConverterBase(ABC):
    version: OdooVersion = None
    migrate_code: bool = True
    prettify: bool = False
    xml_ids: list[dict] = None
    fields_to_rename: list[str] = []

    def __init__(
        self, version: OdooVersion = None, prettify: bool = False, xml_ids: list[dict] = None, migrate_code: bool = True
    ) -> None:
        """Initialize the Converter configuration."""
        self.version: OdooVersion = version
        self.prettify = prettify
        self.xml_ids = xml_ids
        self.migrate_code = migrate_code

    @abstractmethod
    def convert(
        self,
        data: list[dict],
        fields_get: FieldsGetMapping,
        default_get: FieldsGetMapping,
        model: str,
        module: str,
        config: dict,
    ) -> Generator[tuple[dict[Any, Any], Union[str, tuple[str, Any, str, str]]], None, None]:
        raise NotImplementedError("convert method must be implemented in subclass")

    def _rename_fields(self, records: Union[list[dict[str, Any]], dict[str, Any]]):
        if self.migrate_code:
            if isinstance(records, dict):
                records = [records]

            for record in records:
                for field in self.fields_to_rename:
                    if field in record.keys() and record[field]:
                        record[field] = rename_field_base(record[field])
