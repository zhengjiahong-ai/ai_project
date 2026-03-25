import networkx as nx
from bs4 import BeautifulSoup


def build_citation_graph(tei_path):

    graph = nx.DiGraph()

    with open(tei_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "xml")

    refs = soup.find_all("biblStruct")

    for ref in refs:

        title = ref.find("title")

        if title:
            cited = title.get_text()

            graph.add_node(cited)

    return graph