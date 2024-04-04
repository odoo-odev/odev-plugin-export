from pathlib import Path

from .merge_base import MergeBase


class MergeCsv(MergeBase):
    def _merge(self, file_path: Path, file_name: str, record: dict, code: str):
        with open(Path(file_path / file_name)) as f:
            csv_text = f.read()

        # Remove the header from the generated csv files
        return csv_text + "\n" + "\n".join(code.split("\n")[1:])
