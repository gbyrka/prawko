import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from import_catalog import compare_with_active, read_questions


class CatalogDiffTest(unittest.TestCase):
    def test_reimport_keeps_serialized_answers_and_reports_real_changes(self):
        row = {
            "Numer pytania": "102", "Pytanie": "Co oznacza znak?",
            "Odpowiedź A": "Opcja pierwsza", "Odpowiedź B": "Opcja druga", "Odpowiedź C": "Opcja trzecia",
            "Poprawna odp": "B", "Media": "", "Zakres struktury": "SPECJALISTYCZNY",
            "Liczba punktów": "2", "Kategorie": "A,B",
        }
        with patch("import_catalog.xlsx_rows", return_value=[row]):
            prepared, _ = read_questions(Path("unused.xlsx"), "katalog", {})
        question = prepared[0][0]
        with TemporaryDirectory() as directory:
            data = Path(directory)
            (data / "current.json").write_text('{"catalog":"before.json"}', encoding="utf-8")
            previous = [question, {**question, "id": "101"}, {**question, "id": "104"}]
            (data / "before.json").write_text(json.dumps({
                "version": "previous", "questions": previous,
            }), encoding="utf-8")
            current = [question, {**question, "id": "103"}, {**question, "id": "104", "answer": "A"}]
            self.assertEqual(compare_with_active(data, current), {
                "previousVersion": "previous", "added": ["103"], "removed": ["101"], "changed": ["104"],
            })
