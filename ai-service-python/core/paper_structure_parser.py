from bs4 import BeautifulSoup


class PaperSection:

    def __init__(self, title, content):

        self.title = title
        self.content = content


class Paper:

    def __init__(self):

        self.title = ""
        self.abstract = ""
        self.authors = []

        self.sections = []
        self.figures = []
        self.tables = []
        self.citations = []


def parse_paper_structure(tei_path):

    paper = Paper()

    with open(tei_path, "r", encoding="utf-8") as f:

        soup = BeautifulSoup(f, "xml")

    # title
    title_tag = soup.find("title")

    if title_tag:
        paper.title = title_tag.get_text(strip=True)

    # abstract
    abstract_tag = soup.find("abstract")

    if abstract_tag:
        paper.abstract = abstract_tag.get_text(strip=True)

    # authors
    for author in soup.find_all("author"):

        name = author.get_text(strip=True)

        if name:
            paper.authors.append(name)

    # sections
    for div in soup.find_all("div", {"type": "section"}):

        head = div.find("head")

        title = head.get_text(strip=True) if head else "unknown"

        paragraphs = []

        for p in div.find_all("p"):

            paragraphs.append(p.get_text(strip=True))

        content = "\n".join(paragraphs)

        paper.sections.append(
            PaperSection(title, content)
        )

    # figures
    for fig in soup.find_all("figure"):

        caption = fig.get_text(strip=True)

        if caption:
            paper.figures.append(caption)

    # tables
    for table in soup.find_all("table"):

        caption = table.get_text(strip=True)

        if caption:
            paper.tables.append(caption)

    # citations
    for ref in soup.find_all("biblStruct"):

        title = ref.find("title")

        if title:
            paper.citations.append(
                title.get_text(strip=True)
            )

    return paper