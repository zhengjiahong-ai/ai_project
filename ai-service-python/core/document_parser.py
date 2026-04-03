from bs4 import BeautifulSoup


def parse_tei_xml(tei_path):
    """
    解析 GROBID TEI XML
    同时提取标题、作者和摘要作为元数据部分
    """

    with open(tei_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "xml")

    sections = []

    # 1. 提取元数据 (Front Matter)
    metadata_lines = []
    
    # 标题
    title_tag = soup.find("title")
    if title_tag:
        metadata_lines.append(f"Title: {title_tag.get_text(strip=True)}")
    
    # 作者
    authors = []
    for author in soup.find_all("author"):
        pers_name = author.find("persName")
        if pers_name:
            surname = pers_name.find("surname")
            forename = pers_name.find("forename")
            name_parts = []
            if forename: name_parts.append(forename.get_text(strip=True))
            if surname: name_parts.append(surname.get_text(strip=True))
            authors.append(" ".join(name_parts))
    
    if authors:
        metadata_lines.append(f"Authors: {', '.join(authors)}")
    
    # 摘要
    abstract_tag = soup.find("abstract")
    if abstract_tag:
        metadata_lines.append(f"Abstract: {abstract_tag.get_text(strip=True)}")
    
    # 关键词
    keywords = [k.get_text(strip=True) for k in soup.find_all("term")]
    if keywords:
        metadata_lines.append(f"Keywords: {', '.join(keywords)}")

    if metadata_lines:
        sections.append({
            "section": "Front Matter (Metadata)",
            "content": "\n".join(metadata_lines)
        })

    # 2. 解析正文所有包含文本的 div
    for div in soup.find_all("div"):
        head = div.find("head")
        title = head.get_text(strip=True) if head else "unknown"

        paragraphs = []
        for p in div.find_all("p"):
            paragraphs.append(p.get_text(strip=True))
        
        for formula in div.find_all("formula"):
            paragraphs.append("Equation: " + formula.get_text(strip=True))
            
        for fig in div.find_all("figure"):
            paragraphs.append("Figure: " + fig.get_text(strip=True))

        for table in div.find_all("table"):
            paragraphs.append("Table: " + table.get_text(strip=True))

        content = "\n".join(paragraphs)
        if content.strip():
            sections.append({
                "section": title,
                "content": content
            })

    return sections