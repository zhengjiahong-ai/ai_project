from __future__ import annotations

import hashlib
import io
import json
import os
import platform
import shutil
import tempfile
import time
from argparse import ArgumentParser
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from core.document_parser import extract_translation_layout_index
from core.outline_extractor import build_document_outline

from .metrics import score_headings, score_regions


INFINITY_PARSER_STATUS = {
    "name": "Infinity-Parser",
    "paperId": "2506.03197",
    "status": "not_runnable",
    "reason": "No verifiable official code, model artifact, and license were identified for this spike.",
    "substituted": False,
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(manifest_path: Path, workspace_root: Path | None = None) -> dict[str, Any]:
    manifest_path = Path(manifest_path).resolve()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if workspace_root:
        root = Path(workspace_root).resolve()
    elif payload.get("workspaceRoot"):
        root = (manifest_path.parent / str(payload["workspaceRoot"])).resolve()
    else:
        root = manifest_path.parent
    documents = []
    for raw_document in payload.get("documents", []):
        document = dict(raw_document)
        resolved_path = (root / str(document.get("path") or "")).resolve()
        if resolved_path.is_file():
            actual_sha256 = _sha256(resolved_path)
            fixture_status = "available" if actual_sha256 == document.get("sha256") else "checksum_mismatch"
        else:
            actual_sha256 = None
            fixture_status = "missing"
        document.update(
            {
                "resolvedPath": str(resolved_path),
                "actualSha256": actual_sha256,
                "fixtureStatus": fixture_status,
            }
        )
        documents.append(document)
    return {**payload, "documents": documents}


def _flatten_gold_regions(document: dict[str, Any]) -> list[dict[str, Any]]:
    regions = []
    for page in document.get("gold", {}).get("pages", []):
        page_index = page.get("pageIndex")
        for region in page.get("regions", []):
            regions.append({"pageIndex": page_index, **region})
    return regions


def _flatten_layout_regions(layout_index: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    regions = []
    for page_index, page_payload in layout_index.items():
        for region in page_payload.get("excludedZones", []):
            regions.append({"pageIndex": int(page_index), **region})
    return regions


def process_grobid_document(
    document: dict[str, Any],
    output_dir: Path,
    client: Any | None = None,
    outline_builder: Callable[[str, str], list[dict[str, Any]]] = build_document_outline,
) -> dict[str, Any]:
    if client is None:
        from grobid_client.grobid_client import GrobidClient

        client = GrobidClient(
            grobid_server=os.environ.get("GROBID_SERVER_URL", "http://localhost:8070"),
            batch_size=1,
            sleep_time=1,
            timeout=60,
        )

    started_at = time.perf_counter()
    output_dir = Path(output_dir)
    input_dir = output_dir / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    source_pdf = Path(str(document["resolvedPath"]))
    isolated_pdf = input_dir / "paper.pdf"
    shutil.copy2(source_pdf, isolated_pdf)
    client_output = io.StringIO()
    with redirect_stdout(client_output):
        client.process(
            "processFulltextDocument",
            input_path=str(input_dir),
            output=str(output_dir),
            consolidate_citations=False,
            tei_coordinates=True,
        )
    tei_files = list(output_dir.glob("*.tei.xml"))
    if not tei_files:
        raise RuntimeError("GROBID did not produce a TEI XML file.")

    tei_path = tei_files[0]
    outline = outline_builder(str(tei_path), str(isolated_pdf))
    layout_index = extract_translation_layout_index(str(tei_path))
    predicted_headings = [str(item.get("title") or "") for item in outline if item.get("title")]
    predicted_regions = _flatten_layout_regions(layout_index)
    gold = document.get("gold", {})
    annotated_page_indexes = {
        page.get("pageIndex")
        for page in gold.get("pages", [])
        if page.get("pageIndex") is not None
    }
    scored_regions = [
        region for region in predicted_regions if region.get("pageIndex") in annotated_page_indexes
    ]
    excluded_zones_by_page = {
        str(page_index): payload.get("excludedZones", [])
        for page_index, payload in layout_index.items()
    }
    return {
        "id": document.get("id"),
        "status": "success",
        "durationMs": round((time.perf_counter() - started_at) * 1000),
        "outlineCount": len(predicted_headings),
        "regionCount": len(predicted_regions),
        "grobidClientLog": client_output.getvalue().strip(),
        "metrics": {
            "headings": score_headings(predicted_headings, gold.get("headings", [])),
            "regions": score_regions(scored_regions, _flatten_gold_regions(document)),
        },
        "predictedHeadings": predicted_headings,
        "excludedZonesByPage": excluded_zones_by_page,
    }


def run_grobid_batch(
    documents: list[dict[str, Any]],
    processor: Callable[[dict[str, Any], Path], dict[str, Any]],
) -> list[dict[str, Any]]:
    results = []
    for document in documents:
        if document.get("fixtureStatus") != "available":
            results.append(
                {
                    "id": document.get("id"),
                    "status": document.get("fixtureStatus") or "missing",
                    "metrics": None,
                    "error": "Fixture is unavailable or its checksum does not match.",
                }
            )
            continue
        try:
            with tempfile.TemporaryDirectory() as output_dir:
                results.append(processor(document, Path(output_dir)))
        except Exception as error:
            results.append(
                {
                    "id": document.get("id"),
                    "status": "grobid_unavailable",
                    "metrics": None,
                    "error": str(error),
                }
            )
    return results


def build_benchmark_result(manifest: dict[str, Any], documents: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schemaVersion": "1.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "grobid": "0.7.2",
        },
        "candidate": INFINITY_PARSER_STATUS,
        "manifestSchemaVersion": manifest.get("schemaVersion"),
        "documents": documents,
    }


def main() -> int:
    parser = ArgumentParser(description="Run the Pixiu GROBID layout parser benchmark.")
    parser.add_argument("--manifest", type=Path, default=Path(__file__).with_name("fixtures.json"))
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("grobid-results.json"))
    parser.add_argument("--workspace-root", type=Path)
    args = parser.parse_args()

    manifest = load_manifest(args.manifest, args.workspace_root)
    documents = run_grobid_batch(
        manifest.get("documents", []),
        processor=lambda document, output_dir: process_grobid_document(document, output_dir),
    )
    result = build_benchmark_result(manifest, documents)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if all(item.get("status") == "success" for item in documents) else 2


if __name__ == "__main__":
    raise SystemExit(main())
