import ast
import re
from typing import Any, Generator, List, Tuple

import astunparse
import black
from black import InvalidInput

from odev.common.connectors.rpc import FieldsGetMapping
from odev.common.string import indent

from .converter_base import ConverterBase


class ConverterPython(ConverterBase):
    def convert(
        self,
        records: list[dict],
        fields_get: FieldsGetMapping,
        default_get: FieldsGetMapping,
        model: str,
        module: str,
        config: dict,
    ) -> Generator[Tuple[dict[Any, Any], tuple[str, Any, str, str]], None, None]:
        """Serialize the current model to readable python code.
        :return: The python code representation of the current model
        """
        if model == "ir.model":
            return self.export_class(records)
        else:
            raise NotImplementedError(f"Model {model} is not supported by the Python converter.")

        return None

    def export_class(
        self, records: list[dict]
    ) -> Generator[Tuple[dict[Any, Any], tuple[str, Any, str, str]], None, None]:
        for record in records:
            imports = self._prettify(self.generate_imports())
            class_def = self.generate_class_definition(record)
            class_def = self._prettify(class_def)
            fields = self._prettify(self.generate_field_definitions(record), indent_level=4)
            computes = self._prettify(self.generate_compute_definitions(record), indent_level=4)

            yield (record, (imports, class_def, fields, computes))

    def _prettify(self, code: str, indent_level: int = 0) -> str:
        code = indent(code, indent_level)
        try:
            formated_text = black.format_str(code, mode=black.FileMode(line_length=120)).rstrip()
        except InvalidInput:
            formated_text = code.rstrip()
        return formated_text

    def generate_imports(self):
        _imports = ast.ImportFrom(
            module="odoo",
            names=[
                ast.alias(name="models", asname=None),
                ast.alias(name="fields", asname=None),
                ast.alias(name="api", asname=None),
            ],
            level=0,
        )
        return astunparse.unparse(_imports)

    def generate_class_definition(self, record):

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

            if field_data.get("required"):
                _field.keywords.append(ast.keyword(arg="required", value=ast.Constant(value=True, kind=None)))

            if field_data.get("index"):
                _field.keywords.append(ast.keyword(arg="index", value=ast.Constant(value=True, kind=None)))

            if field_data.get("copy"):
                _field.keywords.append(ast.keyword(arg="copy", value=ast.Constant(value=True, kind=None)))

            if field_data.get("translate"):
                _field.keywords.append(ast.keyword(arg="translate", value=ast.Constant(value=True, kind=None)))

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

                if field_data.get("compute"):
                    compute = ast.parse(field_data["compute"])
                else:
                    body = ast.For(
                        target=ast.Name(id="record", ctx=ast.Store()),
                        iter=ast.Name(id="self", ctx=ast.Load()),
                        lineno=0,
                        body=[
                            ast.Assign(
                                lineno=0,
                                targets=[ast.Name(id=f"record.{field_data['name']}", ctx=ast.Store())],
                                value=ast.Constant(value=False, kind=None),
                            ),
                        ],
                        orelse=[],
                    )
                _computes.append(
                    ast.FunctionDef(
                        name=f"_compute_{field_data['name']}",
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
                        body=[compute if field_data.get("compute") else body],
                        decorator_list=[
                            ast.Call(
                                func=ast.Name(id="api.depends", ctx=ast.Load()),
                                args=[
                                    ast.Constant(value=depends, kind=None)
                                    for depends in field_data["depends"].split(",") or []
                                ],
                                keywords=[],
                            ),
                        ],
                        returns=None,
                        type_comment=None,
                    )
                )

                if field_data.get("relation_field"):
                    _computes.append(
                        ast.FunctionDef(
                            name=f"_inverse_{field_data['name']}",
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
                            body=[
                                ast.For(
                                    target=ast.Name(id="record", ctx=ast.Store()),
                                    iter=ast.Name(id="self", ctx=ast.Load()),
                                    lineno=0,
                                    body=[ast.Pass()],
                                    orelse=[],
                                ),
                            ],
                            decorator_list=[],
                            returns=None,
                            type_comment=None,
                        )
                    )

        return astunparse.unparse(_computes) or ""
