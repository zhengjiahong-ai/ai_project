from pathlib import Path

from .models import WorkerOutput, WorkerResult
from .runner import run_job


FIXED_TEMPLATE_TEXT = (Path(__file__).with_name("fixed_template.py")).read_text(encoding="utf-8")

__all__ = ["FIXED_TEMPLATE_TEXT", "WorkerOutput", "WorkerResult", "run_job"]
