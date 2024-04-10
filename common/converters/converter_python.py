import ast
import re
from typing import (
    Any,
    Generator,
    List,
    Tuple,
    Union,
)

import astunparse
import black
from black import InvalidInput

from odev.common.connectors.rpc import FieldsGetMapping
from odev.common.string import indent

from .converter_base import ConverterBase


class ConverterPython(ConverterBase):
    fields_to_rename = ["model", "name", "relation", "related", "depends", "compute"]

    def convert(
        self,
        records: list[dict],
        fields_get: FieldsGetMapping,
        default_get: FieldsGetMapping,
        model: str,
        module: str,
        config: dict,
        imports: dict[str, list] = None,
    ) -> Generator[Tuple[dict[Any, Any], tuple[str, Any, str, str]], None, None]:
        """Serialize the current model to readable python code.
        :return: The python code representation of the current model
        """
        match model:
            case "ir.model":
                return self.export_class(records, config, imports)
            case _:
                raise NotImplementedError(f"Model {model} is not supported by the Python converter.")

    def export_class(
        self, records: list[dict[str, Any]], config: dict[str, Any], imports: dict[str, list] = None
    ) -> Generator[Tuple[dict[Any, Any], tuple[str, Any, str, str]], None, None]:

        for record in records:
            if self.migrate_code:
                self._rename_fields([record])

                for inc_model in config.get("includes", []):
                    if inc_model in record:
                        self._rename_fields(record[inc_model])

            class_imports = self._prettify(self.generate_imports({"odoo": ["models", "fields", "api"]}))
            class_def = self.generate_class_definition(record)
            class_def = self._prettify(class_def)
            fields = self._prettify(self.generate_field_definitions(record), indent_level=4)
            computes = self._prettify(self.generate_compute_definitions(record), indent_level=4)

            yield (record, (class_imports, class_def, fields, computes))

    def export_mig_script(
        self, imports: dict[str, list[str]] = None, models: list[str] = None, fields: list[str] = None
    ) -> str:
        code_import = self._prettify(self.generate_imports(imports))
        code_method = self._prettify(self.generate_migration_script(models, fields), indent_level=4)

        return f"{code_import}\n\n{code_method}"

    def generate_migration_script(self, models: list[str], fields: list[str]) -> str:
        # mig_script = self.__generate_method(migrate)
        # return astunparse.unparse(mig_script)
        return ""

    def export_init(self, imports: dict[Any, Any]) -> str:
        return self._prettify(self.generate_imports(imports))

    def _prettify(self, code: str, indent_level: int = 0) -> str:
        try:
            formated_text = black.format_str(code, mode=black.FileMode(line_length=120)).rstrip()
        except InvalidInput:
            formated_text = code.rstrip()

        return indent(formated_text, indent_level)

    def generate_imports(self, imports: dict[str, list[str]]):
        _imports = []
        for module, names in imports.items():
            _imports.append(
                ast.ImportFrom(
                    module=module,
                    names=[ast.alias(name=name, asname=None) for name in names],
                    level=0,
                )
            )

        return astunparse.unparse(_imports)

    def generate_class_definition(self, record):
        body = []

        if record.get("model", ""):
            body = [
                ast.Assign(
                    lineno=0,
                    targets=[ast.Name(id="_name" if record["state"] == "manual" else "_inherit", ctx=ast.Store())],
                    value=ast.Constant(value=record.get("model", ""), kind=None),
                ),
            ]

        if record.get("name"):
            body.append(
                ast.Assign(
                    lineno=0,
                    targets=[ast.Name(id="_description", ctx=ast.Store())],
                    value=ast.Constant(value=record["name"], kind=None),
                ),
            )

        _class = ast.ClassDef(
            name=record.get("model", "").title().replace(".", "").replace("_", ""),
            bases=[ast.Attribute(value=ast.Name(id="models", ctx=ast.Load()), attr="Model", ctx=ast.Load())],
            body=body,
            keywords=[],
            decorator_list=[],
        )
        return astunparse.unparse(_class)

    # flake8: noqa: C901
    def generate_field_definitions(self, record):
        _fields = []
        for field_data in record.get("ir.model.fields", []):
            _field = ast.Call(
                func=ast.Name(id=f"fields.{field_data['ttype'].capitalize()}", ctx=ast.Load()),
                args=[],
                keywords=[],
            )

            append_string = (
                re.match(
                    field_data["name"],
                    (field_data.get("field_description", "") or "").replace(" ", "_").lower(),
                    flags=re.IGNORECASE,
                )
                is None
                and field_data["field_description"]
            )

            if field_data.get("relation") and field_data["relation"]:
                _field.args.append(ast.Constant(value=field_data["relation"], kind=None))

                if append_string:
                    _field.keywords.append(
                        ast.keyword(arg="string", value=ast.Constant(value=field_data["field_description"], kind=None))
                    )
            else:
                if append_string:
                    _field.args.append(ast.Constant(value=field_data["field_description"], kind=None))

            if field_data.get("selection_ids"):
                selection_list: List[ast.Tuple] = []
                for selection in field_data["ir.model.fields.selection"]:
                    selection_tuple = ast.Tuple(
                        elts=[
                            ast.Constant(value=selection["value"], kind=None),
                            ast.Constant(value=selection["display_name"], kind=None),
                        ],
                        ctx=ast.Load(),
                    )
                    selection_list.append(selection_tuple)
                _field.keywords.append(ast.keyword(arg="selection", value=ast.List(selection_list, ctx=ast.Load())))

            for key in ["required", "index", "copy", "translate"]:
                if field_data.get(key):
                    _field.keywords.append(ast.keyword(arg=key, value=ast.Constant(value=True, kind=None)))

            if field_data.get("depends") or field_data.get("related"):
                if field_data.get("related"):
                    _field.keywords.append(
                        ast.keyword(arg="related", value=ast.Constant(value=field_data["related"], kind=None))
                    )
                else:
                    _field.keywords.append(
                        ast.keyword(
                            arg="compute", value=ast.Constant(value=f"_compute_{field_data['name']}", kind=None)
                        )
                    )

                    if field_data.get("relation_field"):
                        _field.keywords.append(
                            ast.keyword(
                                arg="inverse", value=ast.Constant(value=f"_inverse_{field_data['name']}", kind=None)
                            )
                        )

                if field_data.get("store"):
                    _field.keywords.append(ast.keyword(arg="store", value=ast.Constant(value=True, kind=None)))

                if not field_data.get("readonly"):
                    _field.keywords.append(ast.keyword(arg="readonly", value=ast.Constant(value=False, kind=None)))
            else:
                if field_data.get("readonly"):
                    _field.keywords.append(ast.keyword(arg="readonly", value=ast.Constant(value=True, kind=None)))

            _fields.append(
                ast.Assign(
                    lineno=0,
                    targets=[ast.Name(id=field_data["name"], ctx=ast.Store())],
                    value=_field,
                )
            )

        return astunparse.unparse(_fields) or ""

    def generate_compute_definitions(self, record):
        _computes = []
        for field_data in record.get("ir.model.fields", []):
            if field_data.get("depends"):
                body: Union[ast.For, ast.Module] = None  # type: ignore

                if field_data.get("compute"):
                    body = ast.parse(field_data["compute"])
                else:
                    assignation = ast.Assign(
                        lineno=0,
                        targets=[ast.Name(id=f"record.{field_data['name']}", ctx=ast.Store())],
                        value=ast.Constant(value=False, kind=None),
                    )
                    body = self.__generate_for_loop(assignation)

                _computes.append(
                    self.__generate_method(
                        f"_compute_{field_data['name']}",
                        body,
                        "api.depends",
                        field_data.get("depends").split(",") or [],
                    )
                )

                if field_data.get("relation_field"):
                    body = self.__generate_for_loop(ast.Pass())
                    _computes.append(self.__generate_method(f"_inverse_{field_data['name']}", body))

        return astunparse.unparse(_computes) or ""

    def __generate_method(
        self,
        method_name: str,
        code: Union[ast.For, ast.Module],  # type: ignore
        decorator_name: str = "",
        decorator_list: List[str] = None,
    ) -> ast.FunctionDef:
        return ast.FunctionDef(
            name=method_name,
            lineno=0,
            args=ast.arguments(
                args=[ast.arg(arg="self", annotation=None)],
                posonlyargs=[],
                vararg=None,
                kwonlyargs=[],
                kw_defaults=[],
                kwarg=None,
                defaults=[],
            ),
            body=[code],
            decorator_list=self.__generate_decorator(decorator_name, decorator_list) if decorator_name else [],
            returns=None,
            type_comment=None,
        )

    def __generate_decorator(self, decorator_name: str, data: list[str]) -> List[ast.Call]:
        return [
            ast.Call(
                func=ast.Name(id=decorator_name, ctx=ast.Load()),
                args=[ast.Constant(value=depends, kind=None) for depends in data or []],
                keywords=[],
            )
        ]

    def __generate_for_loop(self, assignation: Union[ast.Pass, ast.Assign] = None) -> ast.For:
        return ast.For(
            target=ast.Name(id="record", ctx=ast.Store()),
            iter=ast.Name(id="self", ctx=ast.Load()),
            lineno=0,
            body=[assignation],
            orelse=[],
        )
