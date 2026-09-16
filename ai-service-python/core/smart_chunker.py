import itertools
import re

CHUNK_SIZE = 900
CHUNK_MAX_SIZE = 1400
CHUNK_OVERLAP = 150
CHUNK_OVERLAP_MAX = 400

# parse_tei_xml 合成的元数据段落（Title/Authors/Abstract/Keywords）。
# 它不是论文页面上的真实正文，入库会让检索片段继承合成文本，故在索引与精读上下文中都剔除。
FRONT_MATTER_SECTION = "Front Matter (Metadata)"

# GROBID 会把公式编号 / 页眉数字误判成章节标题（实测出现过 "8:" 这种标题带着 2500+ 字符正文）。
# 标题没有语义但正文有价值，所以只改标题、不丢内容：并回上一个真实章节。
_NOISE_SECTION_TITLE_RE = re.compile(r"^\d+\s*[:.、)）]?\s*$")
_CONTINUATION_SUFFIX = " (continued)"
_UNKNOWN_SECTION_TITLE = "Body Text"

# 句子边界：英文句末标点后跟空白，或中文句末标点。
# "e.g." / "Fig. 3" 这类缩写会被误切，但句子只是切块的最小单元，
# 边界切偏一个词不影响 chunk 的完整性，代价可接受。
_SENTENCE_END_RE = re.compile(r"[.!?;]\s+|[。！？；]")


def normalize_section_titles(sections):
    """剔除合成元数据段落，并把无语义的纯数字标题并回上一个真实章节。

    只处理标题、不按长度丢弃内容：长度过滤属于精读上下文的预算策略，
    放进索引路径会让短小但真实的章节（小节标题、图表说明）一起消失。
    """
    normalized = []
    last_title = ""

    for section in sections or []:
        if not isinstance(section, dict):
            continue

        title = str(section.get("section") or "").strip()
        if not title or title == FRONT_MATTER_SECTION:
            continue

        if _NOISE_SECTION_TITLE_RE.match(title):
            title = f"{last_title or _UNKNOWN_SECTION_TITLE}{_CONTINUATION_SUFFIX}"
        else:
            last_title = title

        normalized.append({**section, "section": title, "sectionTitle": title})

    return normalized


def _split_sentences(text):
    """按句子边界切分，返回非空句子列表。"""
    pieces = []
    start = 0
    for match in _SENTENCE_END_RE.finditer(text):
        pieces.append(text[start:match.end()])
        start = match.end()
    if start < len(text):
        pieces.append(text[start:])

    return [piece.strip() for piece in pieces if piece.strip()]


def _pack_words(text, size):
    """按空白打包到 size 字符，保证不在词中间断开。"""
    pieces = []
    current = ""
    for word in str(text).split():
        if current and len(current) + 1 + len(word) > size:
            pieces.append(current)
            current = word
        else:
            current = f"{current} {word}" if current else word
    if current:
        pieces.append(current)

    return pieces


def _split_long_line(line):
    """超过 CHUNK_SIZE 的单行降级拆分：句子 -> 词 -> 字符。"""
    sentences = _split_sentences(line)
    if len(sentences) <= 1:
        sentences = [line]

    pieces = []
    for sentence in sentences:
        pieces.extend(_pack_words(sentence, CHUNK_SIZE) or [sentence])

    units = []
    for piece in pieces:
        # 既无句末标点也无空白的超长串（公式序列、粘连表格）只能字符硬切
        while len(piece) > CHUNK_MAX_SIZE:
            units.append(piece[:CHUNK_MAX_SIZE])
            piece = piece[CHUNK_MAX_SIZE:]
        if piece.strip():
            units.append(piece.strip())

    return units


def _split_units(text):
    """把章节正文切成不可再分的语义单元。

    GROBID 用单个换行连接段落，公式/图/表各自成段（以 Equation:/Figure:/Table: 开头），
    所以按行切分天然不会把公式切成两半 —— 这正是旧的 900 字符定长切片做不到的，
    它会在任意位置断开，实测产出过 "ation (QT) technique" 这种半个词开头的片段。
    """
    units = []
    for line in str(text or "").split("\n"):
        line = line.strip()
        if not line:
            continue
        if len(line) <= CHUNK_SIZE:
            units.append(line)
        else:
            units.extend(_split_long_line(line))

    return units


def _pack_units(units):
    """贪心把语义单元打包到 CHUNK_SIZE，块内保留换行结构。"""
    groups = []
    current = []
    current_len = 0

    for unit in units:
        if current and current_len + len(unit) + 1 > CHUNK_SIZE:
            groups.append(current)
            current = []
            current_len = 0
        current.append(unit)
        current_len += len(unit) + (1 if len(current) > 1 else 0)

    if current:
        groups.append(current)

    return groups


def _tail_words(text, limit):
    """取末尾不超过 limit 字符的片段，并丢掉开头可能被切断的半个词。

    中文无空格分隔，此时退化为字符截断 —— 中文以字为单位，截断不构成残词。
    """
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text

    tail = text[-limit:]
    cut = tail.find(" ")
    if cut >= 0:
        tail = tail[cut + 1:]
    return tail.strip()


def _tail_units(previous_group):
    """取上一块末尾的完整单元作为 overlap；单元过大时只截其末尾片段。"""
    selected = []
    total = 0
    for unit in reversed(previous_group):
        candidate = unit
        if total + len(candidate) > CHUNK_OVERLAP_MAX:
            candidate = _tail_words(unit, CHUNK_OVERLAP_MAX - total)
        if not candidate.strip():
            break
        selected.insert(0, candidate.strip())
        total += len(candidate)
        if total >= CHUNK_OVERLAP:
            break

    return selected


def chunk_sections(sections):
    """结构感知切块：段落 -> 句子 -> 词 逐级降级，不切断公式与单词。

    sections:
    [
        {"section":"method","content":"..."}
    ]

    overlap 只在同一章节内部生效：跳章节拼接会把上一节的结论贴到下一节开头，
    既污染语义，也让 chunk 的章节标题与实际内容不一致。
    """
    chunks = []

    for sec in sections or []:
        if not isinstance(sec, dict):
            continue

        text = str(sec.get("content") or "")
        title = sec.get("section")
        section_id = sec.get("id") or sec.get("sectionId") or sec.get("section_id")
        page_index = sec.get("pageIndex") if sec.get("pageIndex") is not None else sec.get("page_index")
        page = sec.get("page")

        groups = _pack_units(_split_units(text))
        if not groups:
            continue

        overlapped = [groups[0]]
        for previous, current in itertools.pairwise(groups):
            overlapped.append(_tail_units(previous) + current)

        for group in overlapped:
            chunk = {
                "section": title,
                "sectionTitle": title,
                "text": "\n".join(group),
            }
            if section_id:
                chunk["sectionId"] = section_id
            if page_index is not None:
                chunk["pageIndex"] = page_index
            if page is not None:
                chunk["page"] = page

            chunks.append(chunk)

    return chunks
