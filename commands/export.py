"""Export data from a database."""

import ast
import copy
import os
import shutil
from collections import defaultdict
from itertools import chain
from pathlib import Path
from typing import (
    Any,
    Dict,
    List,
    Optional,
    Union,
)

import black
import yaml

from odev.common import args, progress
from odev.common.commands import DatabaseCommand
from odev.common.connectors.rpc import ConnectorError
from odev.common.logging import logging
from odev.common.odoobin import OdoobinProcess
from odev.common.version import OdooVersion

from odev.plugins.odev_plugin_export.common.converters.converter_base import ConverterBase
from odev.plugins.odev_plugin_export.common.converters.converter_factory import ConverterFactory
from odev.plugins.odev_plugin_export.common.converters.converter_python import ConverterPython
from odev.plugins.odev_plugin_export.common.merge.merge_factory import MergeFactory
from odev.plugins.odev_plugin_export.common.odoo import DEFAULT_MODULE_LIST, get_xml_ids


logger = logging.getLogger(__name__)


class ExportCommand(DatabaseCommand):
    """Export data from a database."""

    _name = "export"
    _aliases = ["search", "read", "records"]

    model = args.String(name="model", aliases=["-m", "--model"], description="The model to export.")
    domain = args.String(
        aliases=["-d", "--domain"],
        description="The domain to filter the records to export.",
    )
    fields = args.List(
        aliases=["-F", "--fields"],
        description="The fields to export, all fields by default.",
    )
    format = args.String(
        aliases=["-t", "--format"],
        description="The output format.",
        choices=["json", "csv", "xml", "py"],
        default="xml",
    )
    modules = args.List(
        aliases=["--modules"],
        description="Comma-separated list of modules to export",
        default=DEFAULT_MODULE_LIST,
    )
    export_config = args.Path(
        aliases=["-c", "--config"],
        description="Path to an alternative export config file.",
    )
    importable = args.Flag(
        aliases=["-i"],
        description="Create an importable module.",
        default=False,
    )
    no_migrate_code = args.Flag(
        aliases=["-M"],
        description="Do not migrate the manual / studio fields into python fields.",
        default=False,
    )
    path = args.Path(
        aliases=["--path"],
        description="Path to the export template.",
        default=Path(".").resolve(),
    )
    version = args.String(
        aliases=["-V", "--version"],
        description="Target version of the export template.",
        default="master",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.args.path and self.args.path.exists():
            if str(self.odev.path).startswith(str(self.args.path)):
                raise self.error("Odev export can't be launched without --path inside odev folder")

            if not OdoobinProcess.check_addons_path(self.args.path) and len(list(self.args.path.iterdir())):
                raise self.error(
                    f"Path {self.args.path.as_posix()} already exist and doesn't seem to be an Odoo module path"
                )

            if len(list(self.args.path.iterdir())) and self.console.confirm(
                f"The folder {self.args.path} already exist do you want to delete first ?"
            ):
                logger.warning(f"Existing folder '{self.args.path}' successfully deleted")
                shutil.rmtree(self.args.path)

        self.args.path.mkdir(parents=True, exist_ok=True)

        self.args.modules = list(set(self.args.modules + DEFAULT_MODULE_LIST))

        self.export_config = self.__load_config()

    def run(self):
        self.xml_ids, ids_to_export = self.__load_xml_ids(self.export_config.keys())

        self.converter = ConverterFactory(
            version=OdooVersion(self.args.version), xml_ids=self.xml_ids, migrate_code=not self.args.no_migrate_code
        )

        self.converter_py = ConverterPython(
            version=OdooVersion(self.args.version), xml_ids=self.xml_ids, migrate_code=not self.args.no_migrate_code
        )

        # TODO: Add prettify argument as before
        self.merge = MergeFactory(
            version=OdooVersion(self.args.version),
            xml_ids=self.xml_ids,
            path=self.args.path,
            prettify=True,
            migrate_code=not self.args.no_migrate_code,
        )

        for module, data in ids_to_export.items():
            ConverterBase.depends = []
            logger.info(f"Exporting '{module}' module to {Path(self.args.path / module)}")
            for model in data.keys():
                config = self.export_config[model]
                if not config.get("export", True):
                    continue

                if ids := data.get(model, []):
                    self.export(module, model, ids)

            if Path(self.args.path / module).exists():
                self.__generate_init_files(module)
                self.__generate_manifest(module)

    def __generate_init_files(self, module: str):
        """Generate the __init__.py files for the exported module."""

        def generate_init_file(module: str, folder: str, imports: List[str] = None):
            if not imports:
                return

            init_file = Path(self.args.path / module / folder / "__init__.py")

            with init_file.open("w") as f:
                for file_name in imports:
                    if Path(self.args.path / module / folder / f"{file_name}").exists():
                        file_name = file_name.replace(".py", "")
                        f.write(f"from . import {file_name}\n")

        init_folder = [] if self.args.importable else ["models", "controllers"]
        generate_init_file(module, ".", init_folder)

        python_models = [f.name for f in Path(self.args.path / module / "models").glob("*.py")]
        generate_init_file(module, "models", python_models)

    def __generate_manifest(self, module: str):
        """Generate the __manifest__.py file for the export module."""

        manifest_file = Path(self.args.path / module / "__manifest__.py")

        depends = [m for m in ConverterBase.depends if m not in ["base", module]] or ["base"]

        manifest: dict[str, Union[str, List[str]]] = {
            "name": f"{module} export",
            "version": str(self._database.version) + ".1.0.0",
            "depends": depends,
            "data": [],
        }

        for folder in ["data", "views", "security"]:
            for file in Path(self.args.path / module / folder).glob("*"):
                if type(manifest["data"]) == list:
                    manifest["data"].append(f"{folder}/{file.name}")

        with open(manifest_file, "w") as f:
            f.write(black.format_str(str(manifest), mode=black.FileMode(line_length=120)))

    def __generate_mig_script(self, module: str, records: list[dict[str, Any]], config: dict[str, Any]):
        """https://github.com/odoo-ps/ps-tech-odev/blob/main/odev/templates/default/sh/scaffold_pre-10.jinja"""

        imports = {"odoo": ["SUPERUSER_ID", "api"], "odoo.upgrade": ["util"], "logging": [], "os": []}

        mig_script: str = self.converter_py.export_mig_script(imports, records, config)
        mig_script_path = Path(self.args.path, module, "migrations", str(self._database.version) + ".1.0.0")

        if not mig_script:
            return

        mig_script_path.mkdir(parents=True, exist_ok=True)

        with Path(mig_script_path, "pre-10.py").open("w") as f:
            f.write(mig_script)

        with Path(self.args.path, "requirements.txt").open("w") as f:
            f.write("odoo_upgrade @ git+https://github.com/odoo/upgrade-util@master")

    def __load_config(self):
        """Load the config file and override config for importable module if needed
        :return: The config file
        """
        if not (config_file := self.args.export_config):
            config_file = Path(os.path.dirname(__file__)).parent / "export.yaml"

        with open(config_file, "r") as f:
            config = yaml.safe_load(f)

            if self.args.importable:
                for model, conf in config["saas"].items():
                    for key, value in conf.items():
                        config["sh"][model][key] = value

        if any([self.args.model, self.args.domain, self.args.fields]):
            for model in config["sh"]:
                if model != self.args.model:
                    config["sh"][model]["export"] = False

            if model not in config["sh"].keys() and not self.args.fields:
                raise self.error(f"You need to explicitly define a list of fields for exporting '{self.args.model}'")

            if self.args.model not in config["sh"]:
                config["sh"][self.args.model] = {
                    "domain": self.args.domain,
                    "fields": self.args.fields,
                    "format": self.args.format,
                    "file_name_field": self.args.model.replace(".", "_"),
                }

        config["sh"] = dict(sorted(config["sh"].items(), key=lambda x: x[1].get("priority", float("inf"))))

        return config["sh"]

    def __load_xml_ids(self, models):
        """Load the XML IDs from the database.
        :return: The XML IDs and XML IDs to export
        """
        with progress.spinner("Loading all XML IDs"):
            imd = self._database.models["ir.model.data"].search_read(
                [],
                fields=["res_id", "noupdate", "name", "module", "model"],
                order="model, id desc",
            )
            xml_ids = defaultdict(list)
            for i in imd:
                xml_ids[i["model"]].append(i)

        logger.info(f"{len(imd)} XML IDs records loaded")

        with progress.spinner("Loading XML IDs to export"):
            ids_to_export: Dict[str, Dict[str, List[int]]] = defaultdict(
                lambda: {k: [] for k in self.export_config.keys()}
            )

            for model, id_ in xml_ids.items():
                for xml_id in filter(
                    lambda x: x["module"] in self.args.modules and x["model"] in self.export_config.keys(), id_
                ):
                    ids_to_export[xml_id["module"]][model].append(xml_id["res_id"])

            for model, config in self.export_config.items():
                ids = [x["res_id"] for x in xml_ids[model]]
                domain = ast.literal_eval(config.get("domain", "[]"))

                if ids:
                    domain.append(("id", "not in", ids))
                try:
                    ids_ = [x["id"] for x in self._database.models[model].search_read(domain, fields=["id"])]

                    ids_to_export["__export_module__"][model] += ids_
                except ConnectorError:
                    logger.error(f"Failed to load {model} records")

        ids_to_export_count = len(list(chain(*chain(*(m.values() for m in ids_to_export.values())))))
        logger.info(f"{ids_to_export_count} records to export")

        with progress.spinner("Loading records without XML IDs"):
            for module, models in ids_to_export.items():
                for model, config in self.export_config.items():
                    for model_name, inc in config.get("includes", {}).items():
                        if model_name == "ir.model.fields.selection":
                            continue
                        if model_name in models.keys() and inc.get("inverse_name", False):
                            ids_ = [
                                r[inc["inverse_name"]]
                                for r in self._database.models[model_name].search_read(
                                    [["id", "in", models[model_name]]], fields=[inc["inverse_name"]]
                                )
                            ]

                            ids_to_export[module][model] += set(ids_to_export[module][model] + ids_)

        all_records_count = len(list(chain(*chain(*(m.values() for m in ids_to_export.values())))))
        logger.info(f"{all_records_count - ids_to_export_count} orphan records to export")

        return xml_ids, ids_to_export

    def __get_records(self, module: str, model: str, ids: Optional[List[int]] = None, pk: str = "id") -> List[dict]:
        """Get the records to export.
        :param module: The module to export
        :param model: The model to export
        :param ids: List of id to export
        :param pk: Name of the primary key table used to load records
        :param same_module: If True, only export records for the current module
        :return: A list of records to export
        """
        config = self.export_config[model]
        domain = ast.literal_eval(config.get("domain", "[]"))

        if ids:
            domain.append([pk, "in", ids])

        try:
            # TODO: Yield record one by one in case of error
            data = self._database.models[model].search_read(
                domain, fields=config.get("fields", []), order=config.get("order", [])
            )
        except ConnectorError as conn_error:
            logger.debug(f"Failed to export {model} records: {conn_error}")
            return []

        for inc_model, inc_config in config.get("includes", {}).items():
            inc_ids = [r[inc_config["field"]] for r in data]
            inc_data = self.__get_records(module, inc_model, inc_ids, inc_config["inverse_name"])

            same_module_ids = includes_xml_ids = {}
            if inc_config["inverse_name"] != "id":
                includes_xml_ids = get_xml_ids(self.xml_ids, inc_model, [r["id"] for r in inc_data])
                same_module_ids = {
                    x["res_id"]: x
                    for x in includes_xml_ids.values()
                    if x["module"] == module and x["res_id"] is not None
                }

            inc_data_dict = defaultdict(list)
            for record in inc_data:
                if (
                    inc_model == "ir.model.fields"
                    or same_module_ids
                    and record["id"] in same_module_ids
                    or not same_module_ids
                ):
                    inc_data_dict[str(record[inc_config["inverse_name"]])].append(record)

            for record in data:
                if str(record[inc_config["field"]]) in inc_data_dict.keys():
                    record[inc_model] = inc_data_dict[str(record[inc_config["field"]])]

        return data

    def export(self, module: str, model: str, ids: List[int] = None):
        """Export records.
        :param module: The module to export
        :param model: The model to export
        :param ids: List of id to export
        :return: None
        """
        config = self.export_config[model]
        records = self.__get_records(module, model, ids)
        _records = copy.deepcopy(records)

        if not records:
            return

        fields_get = self._database.models[model].fields_get()

        default_get = self._database.models[model].default_get(list(fields_get.keys()))

        tracker = progress.Progress()
        task = tracker.add_task(f"Exporting {len(records)} {model} records", total=len(records))
        tracker.start()

        for record, code in self.converter.convert(records, fields_get, default_get, model, module, config):
            if code:
                file_name, code = self.merge.merge(module, code, model, record, config)

                with open(file_name, "w") as f:
                    f.write(code)

            tracker.update(task, advance=1)

        tracker.stop()

        logger.info(f"Exported {len(records)} {model} records")

        if model == "ir.model":
            logger.info("Exported 'pre-10' migration script")
            self.__generate_mig_script(module, _records, config)
