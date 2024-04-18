import csv
from io import StringIO
from typing import Generator, Tuple

from odev.common.connectors.rpc import FieldsGetMapping

from .converter_base import ConverterBase


class ConverterCsv(ConverterBase):
    fields_to_rename = ["name", "model_id", "group_id"]

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

        self._rename_fields(records, config)

        for record in records:
            items = []
            for field in config["fields"]:

                if relation := fields_get[field].get("relation"):
                    record_metadata = self.get_xml_ids(self.xml_ids, relation, [record[field]], module=module)
                    self._rename_fields(record_metadata[record[field]])
                    record_metadata = record_metadata[record[field]]

                    items.append(record_metadata["xml_id"])
                elif field == "id":
                    record_metadata = self.get_xml_ids(self.xml_ids, model, [record["id"]], module=module)
                    self._rename_fields(record_metadata[record[field]])
                    items.append(record_metadata[record["id"]]["xml_id"])
                else:
                    items.append(str(record.get(field, "")))

            writer.writerow(items)

        yield ({}, output.getvalue())
