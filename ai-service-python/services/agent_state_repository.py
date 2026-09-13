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
                CREATE TABLE IF NOT EXISTS agent_research_tasks_v3 (
                    task_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_messages_v3 (
                    message_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
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
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS debate_results (
                    run_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
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

    def save_research_task(self, task: dict):
        task_id = str(task.get("taskId") or "").strip()
        project_id = str(task.get("projectId") or "").strip()
        if not task_id or not project_id:
            raise ValueError("Research task requires taskId and projectId.")
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "INSERT OR REPLACE INTO agent_research_tasks_v3 (task_id, project_id, payload) VALUES (?, ?, ?)",
                (task_id, project_id, json.dumps(task, ensure_ascii=False)),
            )
            connection.commit()

    def save_message(self, message: dict):
        message_id = str(message.get("messageId") or "").strip()
        task_id = str(message.get("taskId") or "").strip()
        if not message_id or not task_id:
            raise ValueError("Agent message requires messageId and taskId.")
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "INSERT OR REPLACE INTO agent_messages_v3 (message_id, task_id, payload) VALUES (?, ?, ?)",
                (message_id, task_id, json.dumps(message, ensure_ascii=False)),
            )
            connection.commit()

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

    def get_research_task(self, task_id: str) -> dict:
        return self._get_payload("agent_research_tasks_v3", "task_id", task_id)

    def list_research_tasks(self, project_id: str) -> list[dict]:
        normalized = str(project_id or "").strip()
        with closing(sqlite3.connect(self.db_path)) as connection:
            rows = connection.execute(
                "SELECT payload FROM agent_research_tasks_v3 WHERE project_id = ? ORDER BY rowid DESC", (normalized,)
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def list_messages(self, task_id: str) -> list[dict]:
        normalized = str(task_id or "").strip()
        with closing(sqlite3.connect(self.db_path)) as connection:
            rows = connection.execute(
                "SELECT payload FROM agent_messages_v3 WHERE task_id = ? ORDER BY rowid ASC", (normalized,)
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

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
            connection.execute(
                "DELETE FROM debate_results WHERE project_id = ?",
                (normalized_project_id,),
            )
            task_rows = connection.execute(
                "SELECT task_id FROM agent_research_tasks_v3 WHERE project_id = ?", (normalized_project_id,)
            ).fetchall()
            for row in task_rows:
                connection.execute("DELETE FROM agent_messages_v3 WHERE task_id = ?", (row[0],))
            connection.execute("DELETE FROM agent_research_tasks_v3 WHERE project_id = ?", (normalized_project_id,))
            connection.commit()

    # ── Debate result persistence (24-2) ────────────────────────────────────

    def save_debate_result(self, run_id: str, project_id: str, result: dict) -> None:
        """Persist a completed debate result."""
        from datetime import UTC, datetime

        normalized_run_id = str(run_id or "").strip()
        if not normalized_run_id:
            raise ValueError("debate_results requires a non-empty run_id.")
        created_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO debate_results (run_id, project_id, result_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    normalized_run_id,
                    str(project_id or "").strip(),
                    json.dumps(result, ensure_ascii=False),
                    created_at,
                ),
            )
            connection.commit()

    def get_debate_result(self, run_id: str) -> dict | None:
        """Retrieve a persisted debate result, or None if not found."""
        normalized_run_id = str(run_id or "").strip()
        if not normalized_run_id:
            return None
        with closing(sqlite3.connect(self.db_path)) as connection:
            row = connection.execute(
                "SELECT result_json FROM debate_results WHERE run_id = ?",
                (normalized_run_id,),
            ).fetchone()
        if row is None:
            return None
        return json.loads(row[0])

    def list_debate_results(self, project_id: str) -> list[dict]:
        """List all persisted debate results for a project, newest first."""
        normalized_project_id = str(project_id or "").strip()
        if not normalized_project_id:
            return []
        with closing(sqlite3.connect(self.db_path)) as connection:
            rows = connection.execute(
                """
                SELECT run_id, result_json, created_at
                FROM debate_results
                WHERE project_id = ?
                ORDER BY created_at DESC
                """,
                (normalized_project_id,),
            ).fetchall()
        results: list[dict] = []
        for row in rows:
            item = json.loads(row[1])
            item["run_id"] = row[0]
            item["created_at"] = row[2]
            results.append(item)
        return results

    def clear(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute("DELETE FROM agent_projects_v2")
            connection.execute("DELETE FROM agent_runs_v2")
            connection.execute("DELETE FROM agent_messages_v3")
            connection.execute("DELETE FROM agent_research_tasks_v3")
            connection.execute("DELETE FROM agent_plan_reviews_v2")
            connection.execute("DELETE FROM agent_final_reviews_v2")
            connection.execute("DELETE FROM agent_run_artifacts_v2")
            connection.execute("DELETE FROM agent_run_timeline_entries_v2")
            connection.execute("DELETE FROM debate_results")
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
