from abc import ABC, abstractmethod
from typing import (
    Any,
    Dict,
    Generator,
    List,
    Union,
)

from odev.common.connectors.rpc import FieldsGetMapping
from odev.common.logging import logging
from odev.common.version import OdooVersion

from odev.plugins.ps_tech_odev_export.common.odoo import RecordMetaData, get_xml_ids, rename_field_base


logger = logging.getLogger(__name__)


class ConverterBase(ABC):
    version: OdooVersion = None
    migrate_code: bool = True
    prettify: bool = False
    xml_ids: List[Dict] = None
    fields_to_rename: List[str] = []

    depends: List[str] = []

    def __init__(
        self, version: OdooVersion = None, prettify: bool = False, xml_ids: List[Dict] = None, migrate_code: bool = True
    ) -> None:
        """Initialize the Converter configuration."""
        self.version: OdooVersion = version
        self.prettify = prettify
        self.xml_ids = xml_ids
        self.migrate_code = migrate_code

    @abstractmethod
    def convert(
        self,
        data: List[Dict],
        fields_get: FieldsGetMapping,
        default_get: FieldsGetMapping,
        model: str,
        module: str,
        config: Dict,
    ) -> Generator[tuple[Dict[Any, Any], Union[str, tuple[str, Any, str, str]]], None, None]:
        raise NotImplementedError("convert method must be implemented in subclass")

    def _rename_fields(
        self,
        records: Union[Dict[Union[int, str], Any], List[Dict[Union[int, str], Any]]],
        config: Dict[str, Any] = None,
    ):
        if self.migrate_code:
            if isinstance(records, Dict):
                records = [records]

            for record in records:
                for field in self.fields_to_rename:
                    if field in record.keys() and record[field]:
                        record[field] = rename_field_base(record[field])

                    if config:
                        for inc_model in config.get("includes", []):
                            if inc_model in record:
                                self._rename_fields(record[inc_model])

    def get_xml_ids(
        self, xml_ids, model: str = "", ids: List = None, rename_field: bool = False
    ) -> Dict[Union[int, str], RecordMetaData]:
        xml_ids = get_xml_ids(xml_ids, model, ids, rename_field)

        ConverterBase.depends = list(set(ConverterBase.depends + [x["module"] for x in xml_ids.values()]))

        return xml_ids
