import keyword
import re
from typing import TypedDict


DEFAULT_MODULE_LIST = ["__export_module__", "studio_customization"]


class RecordMetaData(TypedDict):
    xml_id: str
    noupdate: bool
    model: str
    name: str
    module: str
    res_id: float


def get_xml_ids(
    xml_ids, model: str = "", ids: list = None, rename_field: bool = False, module: str = ""
) -> dict[int, RecordMetaData]:
    model_clean = model.replace(".", "_")

    default: dict[int, RecordMetaData] = {
        id_: {
            "model": model,
            "name": f"{model_clean}_{id_!s}",
            "noupdate": False,
            "module": "__export_module__",
            "xml_id": "",
            "res_id": id_,
        }
        for id_ in ids
    }

    for xml_id in xml_ids[model]:
        if xml_id["model"] == model and xml_id["res_id"] in ids:
            default[xml_id["res_id"]].update(xml_id)
            default[xml_id["res_id"]]["xml_id"] = (
                f"{xml_id['module']}.{xml_id['name']}" if xml_id["module"] != module else xml_id["name"]
            )

    return default


def rename_field_base(field_name: str) -> str:
    if type(field_name) is str:
        field_name = re.sub(r"(?<=['\W_\s])x_(studio_)?|^x_(studio_)?", r"", field_name)

        if field_name in keyword.kwlist:
            field_name = f"_{field_name}"

    return field_name
