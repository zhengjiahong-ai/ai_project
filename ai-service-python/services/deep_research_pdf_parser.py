"""Isolated public-PDF parsing worker; parent enforces a process deadline."""
import io
import json
import sys

from PyPDF2 import PdfReader


def parse_pdf(body: bytes, max_pages: int) -> list[dict]:
    reader = PdfReader(io.BytesIO(body))
    if reader.is_encrypted or len(reader.pages) > max_pages:
        raise ValueError("Unsupported PDF")
    return [{"page": index + 1, "text": (page.extract_text() or "")[:30000]}
            for index, page in enumerate(reader.pages)]


def main():
    try:
        max_pages, max_bytes = int(sys.argv[1]), int(sys.argv[2])
        if not 1 <= max_pages <= 100 or not 1 <= max_bytes <= 64 * 1024 * 1024:
            return 2
        body = sys.stdin.buffer.read(max_bytes + 1)
        if len(body) > max_bytes:
            return 2
        result = parse_pdf(body, max_pages)
        sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False).encode('utf-8'))
        return 0
    except Exception:
        # Never forward document data or parser diagnostics into the UI/logs.
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
