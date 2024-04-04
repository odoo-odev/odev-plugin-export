import re
import textwrap
from pathlib import Path

import isort

from .merge_base import MergeBase


class MergePython(MergeBase):
    def _merge(self, file_path: Path, file_name: str, record: dict, code: str):
        with open(Path(file_path / file_name), "r") as f:
            text = f.read()

        # Find the class name, find the latest field and add the new fields + compute after it
        def find_last_field_line(text, class_name):
            # Find the class definition
            class_pattern = rf"\s*?(_name|_inherit) = ['\"]{class_name}['\"](.*?)(?=class \w|\Z)"
            class_match = re.search(class_pattern, text, re.DOTALL)

            if class_match:
                class_body = class_match.group(1)

                # Find the last field line
                field_pattern = r"^\s*?\w+ = fields\..*?\)$"
                field_lines = re.findall(field_pattern, class_body, re.MULTILINE | re.DOTALL)

                if field_lines:
                    last_field_line = field_lines[-1].split("\n")[-1]

                    # Find the line number of the last field line
                    line_number = text[: text.rfind(last_field_line)].count("\n") + 1
                    text[: text.rfind('help="Total number of records in this model"')]
                    return last_field_line, line_number

            return None, None

        def replace_import(text, source):
            pattern = r"^(import .*|from .*|^\s*$)*"
            import_lines = re.findall(pattern, text, re.MULTILINE)
            imports_str = "\n".join(import_lines).strip()

            new_import = []
            for line in source.split("\n"):
                if line not in imports_str:
                    new_import.append(line)

            sorted_imports = isort.code(imports_str + "\n" + "\n".join(new_import))

            return text.replace(imports_str, sorted_imports)

        # Adding import on the top, isort will clean them up
        text = replace_import(text, code[0])

        _, line_number = find_last_field_line(text, record["model"])

        lines = text.split("\n")

        lines.insert(line_number or len(lines), textwrap.indent(f"{code[2]}\n{code[3]}", "    "))

        return "\n".join(lines)
