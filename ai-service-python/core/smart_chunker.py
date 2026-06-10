CHUNK_SIZE = 900
CHUNK_OVERLAP = 150


def chunk_sections(sections):
    """
    sections:
    [
        {"section":"method","content":"..."}
    ]
    """

    chunks = []

    for sec in sections:

        text = sec["content"]
        title = sec["section"]
        section_id = sec.get("id") or sec.get("sectionId") or sec.get("section_id")
        page_index = sec.get("pageIndex") if sec.get("pageIndex") is not None else sec.get("page_index")
        page = sec.get("page")

        start = 0

        while start < len(text):

            end = start + CHUNK_SIZE
            chunk_text = text[start:end]

            chunk = {
                "section": title,
                "sectionTitle": title,
                "text": chunk_text,
            }
            if section_id:
                chunk["sectionId"] = section_id
            if page_index is not None:
                chunk["pageIndex"] = page_index
            if page is not None:
                chunk["page"] = page

            chunks.append(chunk)

            start = end - CHUNK_OVERLAP

    return chunks
