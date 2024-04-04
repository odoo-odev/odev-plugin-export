from pathlib import Path

from lxml import etree as ET

from odev.common.logging import logging

from .merge_base import MergeBase


logger = logging.getLogger(__name__)


class MergeXml(MergeBase):
    def _merge(self, file_path: Path, file_name: str, record: dict, code: str):

        try:
            parser = ET.XMLParser(remove_blank_text=True, strip_cdata=False)

            code_root = ET.fromstring(code.encode(), parser)
            file_root = ET.parse(Path(file_path / file_name), parser).getroot()

            file_ids = {elem.get("id") for elem in file_root.xpath("//odoo/* | //odoo/data/*") if elem.get("id")}
            record = code_root.find(".//record")
            record_id = record.get("id")
            is_record_noupdate = bool(len(code_root.xpath("./data")) and code_root.find("./data").get("noupdate"))

            if is_record_noupdate and (
                not len(file_root.xpath("./data")) or not file_root.find("./data").get("noupdate")
            ):
                data = ET.Element("data", {"noupdate": "1"})
                file_root.insert(0, data)

                file_root.attrib.pop("noupdate", None)

            new_root = file_root.find("./data[@noupdate='1']") if is_record_noupdate else file_root

            if record_id in file_ids:
                file_record = file_root.find(f".//*[@id='{record_id}']")
                record_parent_node = file_record.getparent()

                is_elem_noupdate = bool(record_parent_node.get("noupdate"))

                if is_record_noupdate and not is_elem_noupdate:
                    record_parent_node.remove(file_record)

                    new_root.find("./data[@noupdate='1']").append(file_record)
            else:
                new_root.append(record)

            code = ET.tostring(
                file_root,
                encoding="utf-8",
                pretty_print=True,
                xml_declaration=True,
            ).decode("utf-8")

            return code
        except Exception as e:
            raise ValueError(f'Failed merging xml in "{file_name}" with:\n{code}\ncaused by {e}') from e
