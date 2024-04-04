from typing import Any


DEFAULT_MODULE_LIST = ["__export_module__", "studio_customization"]


def get_xml_ids(xml_ids, model: str = "", ids: list = None) -> dict[Any, dict[str, object]]:
    model_clean = model.replace(".", "_")

    default = {
        id: {
            "model": model,
            "name": f"{model_clean}_{str(id)}",
            "noupdate": False,
            "module": "__export_module__",
            "xml_id": "",
            "res_id": None,
        }
        for id in ids
    }

    for xml_id in xml_ids[model]:
        if xml_id["model"] == model and xml_id["res_id"] in ids:
            default[xml_id["res_id"]].update(xml_id)
            default[xml_id["res_id"]]["xml_id"] = f"{xml_id['module']}.{xml_id['name']}"
    return default
