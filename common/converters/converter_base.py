from abc import ABC, abstractmethod
from typing import Any, Generator, Union

from odev.common.connectors.rpc import FieldsGetMapping
from odev.common.logging import logging
from odev.common.version import OdooVersion


logger = logging.getLogger(__name__)


class ConverterBase(ABC):

    version: OdooVersion = None
    prettify: bool = False
    xml_ids: list[dict] = None

    def __init__(self, version: OdooVersion = None, prettify: bool = False, xml_ids: list[dict] = None) -> None:
        """Initialize the Converter configuration."""
        self.version: OdooVersion = version
        self.prettify = prettify
        self.xml_ids = xml_ids

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
