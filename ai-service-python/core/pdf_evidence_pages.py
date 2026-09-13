"""Extract page-bound text for citations, independently of GROBID metadata."""
from PyPDF2 import PdfReader


def extract_evidence_pages(file_path):
    reader = PdfReader(file_path)
    sections = []
    for index, page in enumerate(reader.pages):
        text = (page.extract_text() or "").strip()
        if text:
            sections.append({"section": f"Page {index + 1}", "sectionId": f"page-{index + 1}",
                             "pageIndex": index, "page": index + 1, "content": text})
    return sections
