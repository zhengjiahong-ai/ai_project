from bs4 import BeautifulSoup


def parse_tei_xml(tei_path):
    """
    解析 GROBID TEI XML
    返回：
    [
        {
            "section": "...",
            "content": "..."
        }
    ]
    """

    with open(tei_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "xml")

    sections = []

    # 只解析真正的 section
    for div in soup.find_all("div", {"type": "section"}):
        head = div.find("head")
        title = head.get_text(strip=True) if head else "unknown"

        paragraphs = []

        # 正文
        for p in div.find_all("p"):
            paragraphs.append(p.get_text(strip=True))

        # 公式
        for formula in div.find_all("formula"):
            paragraphs.append("Equation: " + formula.get_text(strip=True))

        # 图
        for fig in div.find_all("figure"):
            paragraphs.append("Figure: " + fig.get_text(strip=True))

        # 表
        for table in div.find_all("table"):
            paragraphs.append("Table: " + table.get_text(strip=True))

        content = "\n".join(paragraphs)

        if content.strip():
            sections.append({
                "section": title,
                "content": content
            })

    return sections