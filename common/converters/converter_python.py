import ast
import copy
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

from odev.plugins.ps_tech_odev_export.common.ast_newline import CustomUnparser, NewLine, unparse

from .converter_base import ConverterBase


class ConverterPython(ConverterBase):
    fields_to_rename = ["model", "name", "relation", "related", "depends", "compute"]

    def convert(
        self,
        records: List[dict],
        fields_get: FieldsGetMapping,
        default_get: FieldsGetMapping,
        model: str,
        module: str,
        config: dict,
        imports: dict[str, List] = None,
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
        self, records: List[dict[str, Any]], config: dict[str, Any], imports: dict[str, List] = None
    ) -> Generator[Tuple[dict[Any, Any], tuple[str, Any, str, str]], None, None]:

        self._rename_fields(records, config)

        for record in records:
            class_imports = self._prettify(self.generate_imports({"odoo": ["models", "fields", "api"]}))
            class_def = self.generate_class_definition(record)
            class_def = self._prettify(class_def)
            fields = self._prettify(self.generate_field_definitions(record), indent_level=4)
            computes = self._prettify(self.generate_compute_definitions(record), indent_level=4)

            yield (record, (class_imports, class_def, fields, computes))

    def export_mig_script(
        self, imports: dict[str, List[str]] = None, models: List[dict[str, Any]] = None, config: dict[str, Any] = None
    ) -> str:
        code_import = self._prettify(self.generate_imports(imports))

        _models = copy.deepcopy(models)
        self._rename_fields(_models, config)

        mapped_models: List[tuple[str, str]] = []
        mapped_fields: List[tuple[str, str, str]] = []

        for old_model, new_model in zip(models, _models):
            if old_model["model"] != new_model["model"]:
                mapped_models.append((old_model["model"], new_model["model"]))

            for index, field in enumerate(old_model.get("ir.model.fields", [])):
                new_field = new_model.get("ir.model.fields", [])[index]
                if field["name"] != new_field.get("name"):
                    mapped_fields.append((old_model["model"], field["name"], new_field.get("name")))

        _method = self._prettify(self.generate_migration_script(mapped_models, mapped_fields), indent_level=0)

        return f"{code_import}\n\n{_method}" if mapped_models or mapped_fields else ""

    def export_init(self, imports: dict[Any, Any]) -> str:
        return self._prettify(self.generate_imports(imports))

    def _prettify(self, code: str, indent_level: int = 0) -> str:
        try:
            formated_text = black.format_str(code, mode=black.FileMode(line_length=120)).rstrip()
        except InvalidInput:
            formated_text = code.rstrip()

        return indent(formated_text, indent_level)

    def generate_imports(self, imports: dict[str, List[str]]):
        _imports: List[Union[ast.Import, ast.ImportFrom]] = []
        for module, names in imports.items():
            if names:
                _imports.append(
                    ast.ImportFrom(
                        module=module,
                        names=[ast.alias(name=name, asname=None) for name in names],
                        level=0,
                    )
                )
            else:
                _imports.append(ast.Import(names=[ast.alias(name=module, asname=None)]))

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
                    body = self.__generate_for_loop(body=assignation)

                _computes.append(
                    self.__generate_method(
                        f"_compute_{field_data['name']}",
                        body,
                        "api.depends",
                        field_data.get("depends").split(",") or [],
                    )
                )

                if field_data.get("relation_field"):
                    body = self.__generate_for_loop(body=ast.Pass())
                    _computes.append(self.__generate_method(f"_inverse_{field_data['name']}", body))

        return astunparse.unparse(_computes) or ""

    def __generate_method(
        self,
        method_name: str,
        code: Union[ast.For, ast.Module, List[ast.Assign]],  # type: ignore
        decorator_name: str = "",
        decorator_list: List[str] = None,
        args: List[str] = None,
    ) -> ast.FunctionDef:
        return ast.FunctionDef(
            name=method_name,
            lineno=0,
            args=ast.arguments(
                args=[ast.arg(arg=args_name, annotation=None) for args_name in args or ["self"]],
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

    def __generate_decorator(self, decorator_name: str, data: List[str]) -> List[ast.Call]:
        return [
            ast.Call(
                func=ast.Name(id=decorator_name, ctx=ast.Load()),
                args=[ast.Constant(value=depends.strip(), kind=None) for depends in data or []],
                keywords=[],
            )
        ]

    def __generate_for_loop(
        self,
        loop_var: List[str] = None,
        var_name: str = "self",
        body: Union[ast.Module, ast.Pass, ast.Assign, List[ast.Expr]] = None,
    ) -> ast.For:
        if not loop_var:
            loop_var = ["record"]

        return ast.For(
            target=ast.Tuple(elts=[ast.Name(id=var, ctx=ast.Store()) for var in loop_var], ctx=ast.Store()),
            iter=ast.Name(id=var_name, ctx=ast.Load()),
            lineno=0,
            body=[body] if isinstance(body, (ast.Module, ast.Pass, ast.Assign)) else body,
            orelse=[],
        )

    def __generate_logger_ast(
        self, message: Union[ast.Constant, ast.BinOp, ast.Expr], log_level: str = "info", logger_id: str = "_logger"
    ) -> ast.Expr:
        return ast.Expr(
            value=ast.Call(
                func=ast.Attribute(value=ast.Name(id=logger_id, ctx=ast.Load()), attr=log_level, ctx=ast.Load()),
                args=[message],
                keywords=[],
            )
        )

    # @TODO : call move_field_to_module and move_field_to_module methods

    def generate_migration_script(self, models: List[tuple[str, str]], fields: List[tuple[str, str, str]]) -> str:
        code: List[Union[ast.Expr, ast.Assign, ast.FunctionDef]] = []
        loop_code = []

        code.append(
            ast.Assign(
                targets=[ast.Name(id="_logger", ctx=ast.Store())],
                value=ast.Call(
                    func=ast.Attribute(value=ast.Name(id="logging", ctx=ast.Load()), attr="getLogger", ctx=ast.Load()),
                    args=[ast.Name(id="__name__", ctx=ast.Load())],
                    keywords=[],
                ),
            )
        )

        code.append(NewLine())

        loop_code.append(
            ast.Assign(
                targets=[ast.Name(id="env", ctx=ast.Store())],
                value=ast.Call(
                    func=ast.Attribute(value=ast.Name(id="util", ctx=ast.Load()), attr="env", ctx=ast.Load()),
                    args=[ast.Name(id="cr", ctx=ast.Load())],
                    keywords=[],
                ),
            )
        )
        loop_code.append(NewLine())

        loop_code.append(self.__generate_mig_loop("field", fields))
        loop_code.append(self.__generate_mig_loop("model", models))

        code.append(self.__generate_method("migrate", loop_code, args=["cr", "version"]))

        return unparse(code)

    def __generate_mig_loop(self, loop_type: str, to_migrate: Union[List[tuple[str, str]], List[tuple[str, str, str]]]):
        code: List[Union[ast.Assign, ast.Expr, ast.For]] = []

        code.append(self.__generate_logger_ast(ast.Constant(value=f"Renaming {loop_type}s")))
        code.append(NewLine())

        # Create AST nodes for the to_rename_models
        code.append(
            ast.Assign(
                targets=[ast.Name(id=f"to_rename_{loop_type}s", ctx=ast.Store())],
                value=ast.Tuple(
                    elts=[
                        ast.Tuple(
                            elts=[ast.Constant(value=v) for v in x],
                            ctx=ast.Load(),
                        )
                        for x in to_migrate
                    ]
                    if to_migrate
                    else [],
                    ctx=ast.Load(),
                ),
            )
        )

        code.append(NewLine())

        model_loop_code: List[
            Union[
                ast.Expr,
            ]
        ] = []

        model_loop_code.append(
            self.__generate_logger_ast(
                ast.BinOp(
                    left=ast.Constant(value="rename model : %s -> %s")
                    if loop_type == "model"
                    else ast.Constant(value="rename field : %s -> %s on %s"),
                    op=ast.Mod(),
                    right=ast.Tuple(
                        elts=[
                            ast.Name(id="old_model", ctx=ast.Load()),
                            ast.Name(id="new_model", ctx=ast.Load()),
                        ]
                        if loop_type == "model"
                        else [
                            ast.Name(id="old_field", ctx=ast.Load()),
                            ast.Name(id="new_field", ctx=ast.Load()),
                            ast.Name(id="model", ctx=ast.Load()),
                        ],
                        ctx=ast.Load(),
                    ),
                )
            )
        )

        # Create AST nodes for the SQL execution
        model_loop_code.append(
            ast.Expr(
                value=ast.Call(
                    func=ast.Attribute(value=ast.Name(id="cr", ctx=ast.Load()), attr="execute", ctx=ast.Load()),
                    args=[
                        ast.Constant(value="UPDATE ir_model SET state='base' WHERE model LIKE %s")
                        if loop_type == "model"
                        else ast.Constant(
                            value="UPDATE ir_model_fields SET state='base' WHERE model LIKE %s AND name LIKE %s"
                        ),
                        ast.List(elts=[ast.Name(id=f"model", ctx=ast.Load())], ctx=ast.Load())
                        if loop_type == "model"
                        else ast.List(
                            elts=[ast.Name(id=f"model", ctx=ast.Load()), ast.Name(id=f"new_field", ctx=ast.Load())],
                            ctx=ast.Load(),
                        ),
                    ],
                    keywords=[],
                )
            )
        )

        # Create AST nodes for the rename_model call
        model_loop_code.append(
            ast.Expr(
                value=ast.Call(
                    func=ast.Attribute(
                        value=ast.Name(id="util", ctx=ast.Load()), attr=f"rename_{loop_type}", ctx=ast.Load()
                    ),
                    args=[
                        ast.Name(id="cr", ctx=ast.Load()),
                        ast.Name(id=f"old_model", ctx=ast.Load()),
                        ast.Name(id=f"new_model", ctx=ast.Load()),
                    ]
                    if loop_type == "model"
                    else [
                        ast.Name(id="cr", ctx=ast.Load()),
                        ast.Name(id=f"model", ctx=ast.Load()),
                        ast.Name(id=f"old_field", ctx=ast.Load()),
                        ast.Name(id=f"new_field", ctx=ast.Load()),
                    ],
                    keywords=[],
                )
            )
        )
        model_loop_code.append(NewLine())
        model_loop_code.append(NewLine())

        code.append(
            self.__generate_for_loop(
                loop_var=["model", "old_field", "new_field"] if loop_type == "field" else ["old_model", "new_model"],
                var_name=f"to_rename_{loop_type}s",
                body=model_loop_code,
            )
        )

        return code
