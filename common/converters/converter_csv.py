import csv
from io import StringIO
from typing import Generator, Tuple

from odev.common.connectors.rpc import FieldsGetMapping

from odev.plugins.ps_tech_odev_export.utils.odoo import get_xml_ids

from .converter_base import ConverterBase


class ConverterCsv(ConverterBase):
    def convert(
        self,
        records: list[dict],
        fields_get: FieldsGetMapping,
        default_get: FieldsGetMapping,
        model: str,
        module: str,
        config: dict,
    ) -> Generator[Tuple[dict, str], None, None]:
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(config["fields"])

        for record in records:
            items = []
            for field in config["fields"]:
                if relation := fields_get[field].get("relation"):
                    record_metadata = get_xml_ids(self.xml_ids, relation, [record[field]])
                    record_metadata = record_metadata[record[field]]

                    items.append(f"{record_metadata['module']}.{record_metadata['name']}")
                else:
                    items.append(str(record.get(field, "")))

            writer.writerow(items)

        yield ({}, output.getvalue())
