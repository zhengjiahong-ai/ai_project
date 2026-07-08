import json
import sqlite3
from contextlib import closing


class AgentStateRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def initialize(self):
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_projects_v2 (
                    project_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_runs_v2 (
                    run_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_plan_reviews_v2 (
                    run_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_final_reviews_v2 (
                    run_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_run_artifacts_v2 (
                    run_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_run_timeline_entries_v2 (
                    run_id TEXT NOT NULL,
                    entry_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (run_id, entry_id)
                )
                """
            )
            connection.commit()

    def save_project(self, project: dict):
        self._save_payload(
            "agent_projects_v2",
            "project_id",
            project.get("projectId"),
            project,
        )

    def save_run(self, run: dict):
        self._save_payload("agent_runs_v2", "run_id", run.get("runId"), run)

    def save_plan_review(self, review: dict):
        self._save_payload(
            "agent_plan_reviews_v2",
            "run_id",
            review.get("runId"),
            review,
        )

    def save_final_review(self, review: dict):
        self._save_payload(
            "agent_final_reviews_v2",
            "run_id",
            review.get("runId"),
            review,
        )

    def save_artifacts(self, artifacts: dict):
        self._save_payload(
            "agent_run_artifacts_v2",
            "run_id",
            artifacts.get("runId"),
            artifacts,
        )

    def append_timeline_entry(self, entry: dict):
        run_id = str(entry.get("runId") or "").strip()
        entry_id = str(entry.get("id") or "").strip()
        if not run_id or not entry_id:
            raise ValueError("Timeline entry requires runId and id.")
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO agent_run_timeline_entries_v2 (run_id, entry_id, payload)
                VALUES (?, ?, ?)
                """,
                (run_id, entry_id, json.dumps(entry, ensure_ascii=False)),
            )
            connection.commit()

    def get_run(self, run_id: str) -> dict:
        return self._get_payload("agent_runs_v2", "run_id", run_id)

    def get_project(self, project_id: str) -> dict:
        return self._get_payload("agent_projects_v2", "project_id", project_id)

    def get_plan_review(self, run_id: str) -> dict:
        return self._get_payload("agent_plan_reviews_v2", "run_id", run_id)

    def get_final_review(self, run_id: str) -> dict:
        return self._get_payload("agent_final_reviews_v2", "run_id", run_id)

    def get_artifacts(self, run_id: str) -> dict:
        return self._get_payload("agent_run_artifacts_v2", "run_id", run_id)

    def list_timeline(self, run_id: str) -> list[dict]:
        with closing(sqlite3.connect(self.db_path)) as connection:
            rows = connection.execute(
                """
                SELECT payload FROM agent_run_timeline_entries_v2
                WHERE run_id = ?
                ORDER BY rowid ASC
                """,
                (run_id,),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def list_projects(self) -> list[dict]:
        return self._list_payloads("agent_projects_v2")

    def list_runs(self, project_id: str | None = None) -> list[dict]:
        runs = self._list_payloads("agent_runs_v2")
        if not project_id:
            return runs
        normalized_project_id = str(project_id or "").strip()
        return [
            item for item in runs
            if str(item.get("projectId") or "").strip() == normalized_project_id
        ]

    def delete_project(self, project_id: str) -> None:
        normalized_project_id = str(project_id or "").strip()
        run_ids = [
            str(item.get("runId") or "").strip()
            for item in self.list_runs(normalized_project_id)
        ]
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "DELETE FROM agent_projects_v2 WHERE project_id = ?",
                (normalized_project_id,),
            )
            for run_id in run_ids:
                connection.execute(
                    "DELETE FROM agent_runs_v2 WHERE run_id = ?",
                    (run_id,),
                )
                connection.execute(
                    "DELETE FROM agent_plan_reviews_v2 WHERE run_id = ?",
                    (run_id,),
                )
                connection.execute(
                    "DELETE FROM agent_final_reviews_v2 WHERE run_id = ?",
                    (run_id,),
                )
                connection.execute(
                    "DELETE FROM agent_run_artifacts_v2 WHERE run_id = ?",
                    (run_id,),
                )
                connection.execute(
                    "DELETE FROM agent_run_timeline_entries_v2 WHERE run_id = ?",
                    (run_id,),
                )
            connection.commit()

    def clear(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute("DELETE FROM agent_projects_v2")
            connection.execute("DELETE FROM agent_runs_v2")
            connection.execute("DELETE FROM agent_plan_reviews_v2")
            connection.execute("DELETE FROM agent_final_reviews_v2")
            connection.execute("DELETE FROM agent_run_artifacts_v2")
            connection.execute("DELETE FROM agent_run_timeline_entries_v2")
            connection.commit()

    def _save_payload(self, table_name: str, id_column: str, item_id: str, payload: dict):
        normalized_id = str(item_id or "").strip()
        if not normalized_id:
            raise ValueError(f"{table_name} requires a non-empty id.")
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                f"INSERT OR REPLACE INTO {table_name} ({id_column}, payload) VALUES (?, ?)",
                (normalized_id, json.dumps(payload, ensure_ascii=False)),
            )
            connection.commit()

    def _get_payload(self, table_name: str, id_column: str, item_id: str) -> dict:
        with closing(sqlite3.connect(self.db_path)) as connection:
            row = connection.execute(
                f"SELECT payload FROM {table_name} WHERE {id_column} = ?",
                (item_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"{table_name}:{item_id} not found")
        return json.loads(row[0])

    def _list_payloads(self, table_name: str) -> list[dict]:
        with closing(sqlite3.connect(self.db_path)) as connection:
            rows = connection.execute(
                f"SELECT payload FROM {table_name} ORDER BY rowid ASC"
            ).fetchall()
        return [json.loads(row[0]) for row in rows]
