"""
Tests for the structured_query module.

Covers: valid SQL queries (SELECT/WHERE/ORDER BY/GROUP BY/LIMIT),
invalid queries (non-SELECT, multi-statement, injection), invalid data,
empty data, and edge cases.
"""

import json
import unittest

from services.structured_query import (
    MAX_DATA_BYTES,
    MAX_QUERY_LENGTH,
    _validate_query,
    query_structured_data,
)

SAMPLE_DATA = json.dumps([
    {"name": "Alice", "age": 30, "dept": "Engineering"},
    {"name": "Bob", "age": 25, "dept": "Marketing"},
    {"name": "Carol", "age": 35, "dept": "Engineering"},
    {"name": "Dave", "age": 28, "dept": "Marketing"},
    {"name": "Eve", "age": 32, "dept": "Finance"},
])


# ── Query validation tests ───────────────────────────────────────────────────

class QueryValidationTests(unittest.TestCase):

    def test_accepts_select_star(self):
        self.assertIsNone(_validate_query("SELECT * FROM data"))

    def test_accepts_select_with_columns(self):
        self.assertIsNone(_validate_query("SELECT name, age FROM data"))

    def test_accepts_select_with_where(self):
        self.assertIsNone(_validate_query("SELECT * FROM data WHERE age > 25"))

    def test_accepts_select_with_order_by(self):
        self.assertIsNone(_validate_query("SELECT * FROM data ORDER BY name ASC"))

    def test_accepts_select_with_group_by(self):
        self.assertIsNone(_validate_query("SELECT dept, COUNT(*) FROM data GROUP BY dept"))

    def test_accepts_select_with_limit(self):
        self.assertIsNone(_validate_query("SELECT * FROM data LIMIT 5"))

    def test_accepts_select_lowercase(self):
        self.assertIsNone(_validate_query("select * from data"))

    def test_accepts_select_with_leading_whitespace(self):
        self.assertIsNone(_validate_query("   SELECT * FROM data"))

    def test_rejects_empty_query(self):
        self.assertIsNotNone(_validate_query(""))

    def test_rejects_whitespace_only_query(self):
        self.assertIsNotNone(_validate_query("   "))

    def test_rejects_insert(self):
        self.assertIsNotNone(_validate_query("INSERT INTO data VALUES (1)"))

    def test_rejects_update(self):
        self.assertIsNotNone(_validate_query("UPDATE data SET x = 1"))

    def test_rejects_delete(self):
        self.assertIsNotNone(_validate_query("DELETE FROM data"))

    def test_rejects_drop(self):
        self.assertIsNotNone(_validate_query("DROP TABLE data"))

    def test_rejects_alter(self):
        self.assertIsNotNone(_validate_query("ALTER TABLE data ADD COLUMN x"))

    def test_rejects_create(self):
        self.assertIsNotNone(_validate_query("CREATE TABLE evil (x)"))

    def test_rejects_multi_statement_injection(self):
        self.assertIsNotNone(_validate_query("SELECT * FROM data; DROP TABLE data"))

    def test_rejects_query_exceeding_max_length(self):
        long_query = "SELECT " + "x, " * (MAX_QUERY_LENGTH // 3) + "y FROM data"
        self.assertIsNotNone(_validate_query(long_query))


# ── Integration tests ────────────────────────────────────────────────────────

class StructuredQueryIntegrationTests(unittest.TestCase):

    def test_select_all(self):
        result = query_structured_data("SELECT * FROM data", SAMPLE_DATA)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["rowCount"], 5)
        self.assertEqual(len(result["rows"]), 5)

    def test_select_columns(self):
        result = query_structured_data("SELECT name, age FROM data", SAMPLE_DATA)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["rowCount"], 5)
        self.assertIn("name", result["rows"][0])
        self.assertIn("age", result["rows"][0])
        self.assertNotIn("dept", result["rows"][0])

    def test_select_where_numeric(self):
        result = query_structured_data(
            "SELECT * FROM data WHERE age > 30", SAMPLE_DATA
        )
        self.assertEqual(result["status"], "success")
        names = {r["name"] for r in result["rows"]}
        self.assertEqual(names, {"Carol", "Eve"})

    def test_select_where_string(self):
        result = query_structured_data(
            "SELECT * FROM data WHERE dept = 'Engineering'", SAMPLE_DATA
        )
        self.assertEqual(result["status"], "success")
        names = {r["name"] for r in result["rows"]}
        self.assertEqual(names, {"Alice", "Carol"})

    def test_select_order_by_asc(self):
        result = query_structured_data(
            "SELECT name FROM data ORDER BY name ASC", SAMPLE_DATA
        )
        self.assertEqual(result["status"], "success")
        names = [r["name"] for r in result["rows"]]
        self.assertEqual(names, ["Alice", "Bob", "Carol", "Dave", "Eve"])

    def test_select_order_by_desc(self):
        result = query_structured_data(
            "SELECT name FROM data ORDER BY name DESC", SAMPLE_DATA
        )
        self.assertEqual(result["status"], "success")
        names = [r["name"] for r in result["rows"]]
        self.assertEqual(names, ["Eve", "Dave", "Carol", "Bob", "Alice"])

    def test_select_group_by_count(self):
        result = query_structured_data(
            "SELECT dept, COUNT(*) AS cnt FROM data GROUP BY dept ORDER BY cnt DESC",
            SAMPLE_DATA,
        )
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["rowCount"], 3)
        # Tied counts have undefined order; check the data is correct.
        dept_counts = {r["dept"]: r["cnt"] for r in result["rows"]}
        self.assertEqual(dept_counts["Engineering"], 2)
        self.assertEqual(dept_counts["Marketing"], 2)
        self.assertEqual(dept_counts["Finance"], 1)

    def test_select_limit(self):
        result = query_structured_data(
            "SELECT * FROM data LIMIT 2", SAMPLE_DATA
        )
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["rowCount"], 2)

    def test_select_complex(self):
        result = query_structured_data(
            "SELECT dept, COUNT(*) AS cnt, MIN(age) AS youngest "
            "FROM data WHERE age >= 28 GROUP BY dept ORDER BY cnt DESC",
            SAMPLE_DATA,
        )
        self.assertEqual(result["status"], "success")
        self.assertGreaterEqual(result["rowCount"], 2)

    def test_nested_json_data(self):
        nested = json.dumps([
            {"id": 1, "meta": {"city": "NYC", "zip": "10001"}},
            {"id": 2, "meta": {"city": "LA", "zip": "90001"}},
        ])
        result = query_structured_data("SELECT * FROM data", nested)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["rowCount"], 2)
        # Nested objects are JSON-serialized as TEXT
        self.assertIn("city", result["rows"][0]["meta"])

    def test_empty_array_data(self):
        result = query_structured_data("SELECT * FROM data", "[]")
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["rowCount"], 0)
        self.assertEqual(result["rows"], [])

    def test_non_array_data_rejected(self):
        result = query_structured_data("SELECT * FROM data", '{"x": 1}')
        self.assertEqual(result["status"], "error")
        self.assertIn("array", result["error"])

    def test_invalid_json_data(self):
        result = query_structured_data("SELECT * FROM data", "not json")
        self.assertEqual(result["status"], "error")
        self.assertIn("Invalid JSON", result["error"])

    def test_empty_data_rejected(self):
        result = query_structured_data("SELECT * FROM data", "")
        self.assertEqual(result["status"], "error")
        self.assertIn("empty", result["error"].lower())

    def test_empty_query_rejected(self):
        result = query_structured_data("", SAMPLE_DATA)
        self.assertEqual(result["status"], "error")

    def test_non_select_rejected(self):
        result = query_structured_data(
            "INSERT INTO data VALUES (1)", SAMPLE_DATA
        )
        self.assertEqual(result["status"], "error")
        self.assertIn("Only SELECT", result["error"])

    def test_injection_multi_statement_rejected(self):
        result = query_structured_data(
            "SELECT * FROM data; DROP TABLE data", SAMPLE_DATA
        )
        self.assertEqual(result["status"], "error")
        self.assertIn("Multiple SQL", result["error"])

    def test_injection_drop_in_select_rejected(self):
        result = query_structured_data(
            "SELECT * FROM data WHERE 1=1; DELETE FROM data", SAMPLE_DATA
        )
        self.assertEqual(result["status"], "error")

    def test_invalid_sql_rejected(self):
        result = query_structured_data(
            "SELECT * FROM nonexistent_table", SAMPLE_DATA
        )
        self.assertEqual(result["status"], "error")
        self.assertIn("SQL error", result["error"])

    def test_data_exceeding_max_bytes(self):
        huge = json.dumps([{"x": "y" * (MAX_DATA_BYTES // 2)}] * 2)
        result = query_structured_data("SELECT * FROM data", huge)
        self.assertEqual(result["status"], "error")
        self.assertIn("exceeds maximum", result["error"])

    def test_query_exceeding_max_length(self):
        long_query = "SELECT " + "x, " * (MAX_QUERY_LENGTH // 3) + "y FROM data"
        result = query_structured_data(long_query, SAMPLE_DATA)
        self.assertEqual(result["status"], "error")
        self.assertIn("exceeds maximum", result["error"])


if __name__ == "__main__":
    unittest.main()
