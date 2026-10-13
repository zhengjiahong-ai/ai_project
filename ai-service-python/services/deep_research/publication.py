"""Deliver durable publication events without invoking models or retrieval."""
import threading
from urllib.parse import quote

import requests


class PublicationDispatcher:
    def __init__(self, repo, *, origin, post=requests.post):
        self.repo, self.origin, self.post = repo, origin.rstrip("/"), post
        self.stop_event = threading.Event()
        self.thread = None

    def deliver_once(self):
        delivered = 0
        for event in self.repo.pending_publications():
            if self.stop_event.is_set():
                break
            url = f"{self.origin}/task-workspaces/{quote(event['taskId'], safe='')}/research/{quote(event['runId'], safe='')}/publication-sync"
            try:
                response = self.post(url, json={}, timeout=5, allow_redirects=False)
                body = response.json() if response.status_code == 200 else {}
                if (body.get("status") == "success" and body.get("runId") == event["runId"]
                        and body.get("reportVersionId") == event["payload"].get("reportVersionId")):
                    self.repo.acknowledge_outbox(event["runId"], event["seq"])
                    delivered += 1
            except (requests.RequestException, ValueError, TypeError):
                pass
        return delivered

    def start(self):
        def dispatch():
            while not self.stop_event.is_set():
                try:
                    self.deliver_once()
                except Exception:
                    pass  # Pending events remain durable for the next delivery.
                self.stop_event.wait(5)
        self.thread = threading.Thread(target=dispatch, name="research-publications", daemon=True)
        self.thread.start()

    def shutdown(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=6)
