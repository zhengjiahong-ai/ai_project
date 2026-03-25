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

        start = 0

        while start < len(text):

            end = start + CHUNK_SIZE
            chunk_text = text[start:end]

            chunks.append({
                "section": title,
                "text": chunk_text
            })

            start = end - CHUNK_OVERLAP

    return chunks