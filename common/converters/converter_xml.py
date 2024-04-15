from io import StringIO
from typing import (
    Any,
    Generator,
    List,
    Literal,
    Mapping,
    MutableMapping,
    Tuple,
    TypedDict,
    Union,
    cast,
)

from lxml import etree

from odev.common.connectors.rpc import FieldsGetMapping, RecordData

from odev.plugins.ps_tech_odev_export.common.odoo import DEFAULT_MODULE_LIST, get_xml_ids

from .converter_base import ConverterBase


RecordMetaData = TypedDict("RecordMetaData", {"xml_id": str, "noupdate": bool})

RPC_DATA_CACHE: MutableMapping[str, MutableMapping[int, RecordData]] = {}
RPC_FIELDS_CACHE: MutableMapping[str, FieldsGetMapping] = {}


class ConverterXml(ConverterBase):
    fields_to_rename = [
        "module",
        "name",
        "model_name",
        "model",
        "model_id",
        "res_model",
        "report_name",
        "filter_domain",
        "domain",
        "code",
        "sort",
        "context",
        "domain_force",
        "arch",
        "xml_id",
    ]

    def __convert_xml_many2one(
        self,
        node: etree._Element,
        fields_get: Mapping[str, Mapping[str, Union[str, bool]]],
        value: Union[Literal[False], int],
    ) -> None:
        """Serialize a many2one field to XML.
        :param node: The XML node to serialize the field to
        :param field: The name of the field to serialize
        :param value: The value of the field to serialize
        """
        if value is False:
            node.set("eval", str(value))
        else:
            field = cast(str, node.get("name"))
            record_metadata = get_xml_ids(self.xml_ids, fields_get[field]["relation"], [value])
            self._rename_fields(record_metadata[value])
            node.set("ref", record_metadata[value]["xml_id"])

    def __convert_xml_x2many(self, node: etree._Element, fields_get: FieldsGetMapping, value: List[int]) -> None:
        """Serialize a x2many field to XML.
        :param node: The XML node to serialize the field to
        :param field: The name of the field to serialize
        :param value: The value of the field to serialize
        """
        field = cast(str, node.get("name"))
        linked_record_metadata = get_xml_ids(self.xml_ids, fields_get[field]["relation"], value)
        self._rename_fields(linked_record_metadata)

        def _link_command(metadata: RecordMetaData):
            linked_record_ref = f"ref('{metadata['xml_id']}')"
            return f"Command.link({linked_record_ref})" if self.version.major >= 14 else f"(4, {linked_record_ref})"

        commands = ", ".join(_link_command(metadata) for metadata in linked_record_metadata.values())
        node.set("eval", f"[{commands}]")

    def __convert_xml_any(self, node: etree._Element, fields_get: FieldsGetMapping, value: Any) -> None:
        """Serialize a field to XML.
        :param node: The XML node to serialize the field to
        :param field: The name of the field to serialize
        :param value: The value of the field to serialize
        """
        if value is False or value is True:
            node.set("eval", str(value))
        elif self._name == "ir.ui.view" and node.get("name") == "arch":
            parser = etree.XMLParser(remove_blank_text=True, strip_cdata=False)
            arch = etree.parse(StringIO(value), parser).getroot()

            if arch.tag == "data":
                for element in arch.iterchildren():
                    node.append(element)
            else:
                node.append(arch)
        elif node.get("name") == "code" and fields_get.get("code")["type"] == "text":
            cdata = etree.CDATA(value)
            node.text = cdata
        else:
            node.text = str(value)

    def convert(
        self,
        records: list[dict],
        fields_get: FieldsGetMapping,
        default_get: FieldsGetMapping,
        model: str,
        module: str,
        config: dict,
    ) -> Generator[Tuple[dict, str], None, None]:
        """Serialize records with the given ids to XML.
        :param ids: The ids of the records to serialize
        :param fields: The fields to serialize, all fields by default
        :return: The XML representation of the records with the given ids
        """
        self._name = model

        record_metadatas = get_xml_ids(self.xml_ids, model, [r["id"] for r in records])

        root = etree.Element("odoo")

        self._rename_fields(records, config)

        for record in records:
            record_metadata = record_metadatas[record["id"]]
            self._rename_fields(record_metadata)

            root = etree.Element("odoo")
            if record_metadata["noupdate"]:
                _root = root
                root = etree.SubElement(root, "data", {"noupdate": str(int(record_metadata["noupdate"]))})

            module_name = (
                f"{record_metadata['module']}."
                if record_metadata.get("module", DEFAULT_MODULE_LIST[0]) != module
                else ""
            )
            record["__xml_id"] = f"{module_name}{record_metadata['name']}"

            record_node = etree.SubElement(
                root,
                "record",
                {"id": record["__xml_id"], "model": model},
            )

            fields_order = config["fields"]
            sorted_items = sorted(
                record.items(), key=lambda x: fields_order.index(x[0]) if x[0] in fields_order else float("inf")
            )

            for field, value in sorted_items:
                if field in ("id", "__xml_id") or field not in fields_get:
                    continue

                if field in default_get.keys() and value == default_get[field]:
                    continue

                field_node = etree.SubElement(record_node, "field", {"name": field})

                match fields_get[field]["type"]:
                    case "many2one":
                        value = cast(Union[int, Literal[False]], value)
                        self.__convert_xml_many2one(field_node, fields_get, value)
                    case "one2many" | "many2many":
                        value = cast(List[int], value)
                        self.__convert_xml_x2many(field_node, fields_get, value)
                    case "boolean":
                        value = cast(bool, value)
                        field_node.text = str(value)
                    case _:
                        self.__convert_xml_any(field_node, fields_get, value)

            if record_metadata["noupdate"]:
                root = _root

            etree.indent(root, space=" " * 4)

            xml = etree.tostring(
                root,
                pretty_print=True,
                xml_declaration=True,
                encoding="utf-8",
            ).decode("utf-8")

            yield (record, xml)
