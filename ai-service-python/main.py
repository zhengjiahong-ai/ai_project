# ai-service-python/main.py
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
import os
import tempfile
from grobid_client.grobid_client import GrobidClient
import json
from pydantic import BaseModel
from dotenv import load_dotenv
#from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
import dashscope
from dashscope import Generation
from langchain.llms.base import LLM
from typing import Any, List, Mapping, Optional, Dict
from bs4 import BeautifulSoup  # 👈 必须添加
import shutil                  # 用于清理临时文件夹
# RAG
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from core.rag_vector_db import LiteratureRAG
from core.hybrid_retriever import HybridRetriever

# 延迟初始化rag，避免启动时因模型下载失败而崩溃
rag = None
hybrid = None

def get_rag():
    global rag
    if rag is None:
        try:
            rag = LiteratureRAG()
        except Exception as e:
            print(f"RAG初始化失败: {str(e)}")
            # 提供一个空实现，确保服务能够启动
            class DummyRAG:
                def retrieve(self, query, top_k=3, filter_metadata=None):
                    return []
                def add_literature_to_db(self, file_path, metadata=None):
                    return 0
                def get_db_stats(self):
                    return 0
            rag = DummyRAG()
    return rag
def get_hybrid():
    global hybrid
    if hybrid is None:
        hybrid =HybridRetriever(get_rag())
    return hybrid

# 加载环境变量
load_dotenv()

class CustomDashScopeLLM(LLM):
    """自定义 DashScope LLM 类，适配 langchain 的 LLM 接口"""
    model: str = "qwen-max"  # 默认模型
    temperature: float = 0.3  # 温度系数
    dashscope_api_key: Optional[str] = None  # API Key
    
    @property
    def _llm_type(self) -> str:
        return "dashscope"
    
    def _call(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        **kwargs: Any,
    ) -> str:
        """核心调用方法，实现 langchain 接口"""
        # 配置 API Key
        if self.dashscope_api_key:
            dashscope.api_key = self.dashscope_api_key
        elif os.environ.get("DASHSCOPE_API_KEY"):
            dashscope.api_key = os.environ.get("DASHSCOPE_API_KEY")
        else:
            raise ValueError("未配置 DASHSCOPE_API_KEY")
        
        # 调用 DashScope 官方 API
        try:
            response = Generation.call(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
                result_format="message",
                stream=False
            )
            
            if response.status_code == 200:
                return response.output.choices[0].message.content
            else:
                raise Exception(f"DashScope 调用失败: {response.code} - {response.message}")
        except Exception as e:
            raise Exception(f"LLM 调用异常: {str(e)}")
    
    @property
    def _identifying_params(self) -> Mapping[str, Any]:
        """返回模型标识参数，适配 langchain 接口"""
        return {
            "model": self.model,
            "temperature": self.temperature,
        }


# 定义请求模型
class TermExplainRequest(BaseModel):
    term: str
    context: str

class SocraticQuestionRequest(BaseModel):
    paper_content: str
    reading_progress: str

class BackgroundKnowledgeRequest(BaseModel):
    paper_topic: str
    user_knowledge_level: str


class ChatRequest(BaseModel):
    """简单对话请求：仅用户消息，快速响应"""
    message: str
    pdfId: Optional[Any] = None


app = FastAPI()

# 初始化GROBID客户端
grobid_client = GrobidClient(
    grobid_server="http://grobid:8070",
    batch_size=1,
    sleep_time=1,
    timeout=60
)

# grobid_client=None #测试

# 初始化LLM
#llm = ChatOpenAI(model_name="gpt-4o", temperature=0.3)
# 从环境变量中获取 API 密钥
api_key = os.environ.get("DASHSCOPE_API_KEY")
if not api_key:
    raise ValueError("请在 .env 文件中设置 DASHSCOPE_API_KEY 环境变量")
llm = CustomDashScopeLLM(model="qwen-max", temperature=0.3, dashscope_api_key=api_key)

# 定义摘要模板
summary_template = PromptTemplate(
    input_variables=["text", "section"],
    template="请对以下论文{section}部分进行简洁明了的总结，突出核心内容和关键信息：\n\n{text}\n\n总结："
)

summary_chain = LLMChain(llm=llm, prompt=summary_template)

# 论文结构化抽取链
structure_template = PromptTemplate(
    input_variables=["text"],
    template="""
你是一名学术论文结构分析专家。
请从以下论文内容中提取结构化信息，必须返回JSON格式：

{
    "research_problem": "",
    "core_hypothesis": "",
    "method_framework": [],
    "claimed_contributions": [],
    "experimental_logic": "",
    "limitations": ""
}

论文内容：
{text}
"""
)

structure_chain = LLMChain(llm=llm, prompt=structure_template)

@app.get("/")
def read_root():
    return {"message": "AI Paper Assistant Service is Running"}

import json # 确保顶部导入了 json

@app.post("/api/analyze-pdf")
async def deconstruct_paper(file: UploadFile = File(...)):
    """
    优化版：合并 AI 请求，减少网络等待，防止 Broken Pipe
    """
    input_dir = tempfile.mkdtemp()
    output_dir = tempfile.mkdtemp()
    
    try:
        # 1. 消耗 UploadFile 写入磁盘
        file_path = os.path.join(input_dir, "target_paper.pdf")
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)

        # 2. 调用 GROBID
        grobid_client.process(
            "processFulltextDocument",
            input_path=input_dir,
            output=output_dir,
            consolidate_citations=False, # 👈 改为 False，不再联网查 DOI
            tei_coordinates=True
        )

        # 3. 获取 XML
        xml_files = [f for f in os.listdir(output_dir) if f.endswith('.tei.xml')]
        if not xml_files:
            raise Exception("GROBID 解析失败：未找到生成的 XML。")
            
        tei_file = os.path.join(output_dir, xml_files[0])
        
        # 4. 提取章节内容
        with open(tei_file, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f, 'xml')
            
        # 核心改进：更灵活的章节容器
        sections = {
            "abstract": "",
            "introduction": "",
            "methods": "",
            "results": "",
            "discussion": "",
            "conclusion": ""
        }
        
        # --- A. 专门处理 Abstract (GROBID 通常放在特定标签) ---
        abstract_tag = soup.find('abstract')
        if abstract_tag:
            sections["abstract"] = abstract_tag.get_text(separator=' ', strip=True)

        # --- B. 增强型章节匹配逻辑 ---
        for div in soup.find_all('div'):
            head = div.find('head')
            if head:
                head_text = head.get_text().lower()
                # 提取该 div 下所有段落文本
                p_text = " ".join([p.get_text(separator=' ', strip=True) for p in div.find_all('p')])
                
                # 模糊匹配关键词组，提高命中率
                if any(kw in head_text for kw in ['intro', 'background', 'preliminar']):
                    sections["introduction"] += p_text
                elif any(kw in head_text for kw in ['method', 'approach', 'model', 'design', 'implementation']):
                    sections["methods"] += p_text
                elif any(kw in head_text for kw in ['result', 'experiment', 'evaluation', 'finding']):
                    sections["results"] += p_text
                elif any(kw in head_text for kw in ['discuss', 'limitation', 'related work']):
                    sections["discussion"] += p_text
                elif any(kw in head_text for kw in ['conclu', 'summary', 'future']):
                    sections["conclusion"] += p_text

        # 4. 构建 AI 批量总结上下文
        combined_context = ""
        for name, text in sections.items():
            content_snippet = text.strip()
            if len(content_snippet) > 50:
                # 截断每个章节，保留前 2500 字符，确保不超大模型窗口
                combined_context += f"### 章节: {name.upper()}\n内容: {content_snippet[:2500]}\n\n"

        # 初始化paper_structure变量
        paper_structure = {}
        
        if combined_context:
            # 改进 Prompt，强制要求 JSON 且处理“未识别”的情况
            batch_prompt = f"""
            你是一个学术论文精读专家。请根据以下提取的论文各部分内容，生成每部分的精炼总结。
            
            要求：
            1. 必须返回标准 JSON 格式。
            2. 键名(Key)固定为：abstract, introduction, methods, results, discussion, conclusion。
            3. 如果某部分内容包含“未在该论文中识别到”，请尝试根据其他章节的信息进行推断总结。
            4. 语言使用专业中文，每部分 150 字以内。
            
            论文提取内容：
            {combined_context}
            """
            
            raw_response = llm._call(prompt=batch_prompt)
            
            try:
                # 处理大模型可能带有的 Markdown 修饰语
                clean_json = raw_response.strip()
                if "```json" in clean_json:
                    clean_json = clean_json.split("```json")[1].split("```")[0].strip()
                elif "```" in clean_json:
                    clean_json = clean_json.split("```")[1].split("```")[0].strip()
                
                section_summaries = json.loads(clean_json)
                # 论文结构化抽取
                structure_raw = structure_chain.run(text=combined_context)

                try:
                    clean_struct = structure_raw.strip()
                    if "```" in clean_struct:
                        clean_struct = clean_struct.split("```")[1]
                    paper_structure = json.loads(clean_struct)
                except Exception as e:
                    print(f"结构解析失败: {str(e)}")
                    paper_structure = {"error": "structure_parse_failed", "raw": structure_raw[:500]}
            except Exception as e:
                print(f"JSON解析异常: {str(e)}")
                # 降级处理：如果解析失败，直接返回原始文本
                section_summaries = {"error": "解析失败", "raw": raw_response[:500]}
                paper_structure = {"error": "structure_parse_failed", "raw": "JSON解析异常"}
        else:
            section_summaries = {k: "未能从PDF中识别出有效文字，请确认PDF是否为扫描件。" for k in sections.keys()}
            paper_structure = {"error": "no_content", "raw": "未能从PDF中识别出有效文字"}

        return JSONResponse({
            "status": "success",
            "paper_skeleton": section_summaries,
            "paper_structure": paper_structure
        })

    except Exception as e:
        print(f"分析出错: {str(e)}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
    finally:
        if os.path.exists(input_dir): shutil.rmtree(input_dir)
        if os.path.exists(output_dir): shutil.rmtree(output_dir)
        
@app.post("/api/background-knowledge")
async def get_background_knowledge(request: BackgroundKnowledgeRequest):
    """动态背景补课系统"""
    try:
        paper_topic = request.paper_topic
        user_knowledge_level = request.user_knowledge_level
        
        # 定义背景知识推荐模板
        background_template = PromptTemplate(
            input_variables=["paper_topic", "user_knowledge_level"],
            template="请根据以下论文主题和用户知识水平，推荐用户需要了解的前置基础知识：\n\n论文主题：{paper_topic}\n用户知识水平：{user_knowledge_level}\n\n要求：\n1. 识别用户理解该论文所需的核心前置概念和理论\n2. 按知识依赖关系排序（从基础到高级）\n3. 对每个推荐的知识点提供简要说明和学习资源建议\n4. 考虑用户当前知识水平，确保推荐内容既不过于简单也不过于困难\n\n推荐的前置知识："
        )
        
        background_chain = LLMChain(llm=llm, prompt=background_template)
        background_knowledge = background_chain.run(paper_topic=paper_topic, user_knowledge_level=user_knowledge_level)
        
        # 解析推荐的知识
        knowledge_items = [item.strip() for item in background_knowledge.split('\n') if item.strip()]
        
        return JSONResponse({
            "status": "success",
            "paper_topic": paper_topic,
            "user_knowledge_level": user_knowledge_level,
            "background_knowledge": knowledge_items
        })
        
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.post("/api/socratic-questions")
async def generate_socratic_questions(request: SocraticQuestionRequest):
    """引导式学习引擎（苏格拉底式提问）（融合RAG检索）"""
    try:
        paper_content = request.paper_content
        reading_progress = request.reading_progress

        # ===== 新增：RAG检索相关片段 =====
        rag_query = f"基于论文内容生成苏格拉底式问题，阅读进度：{reading_progress}，论文内容：{paper_content[:300]}"
        rag_results = hybrid.retrieve(rag_query)["vector"]
        rag_context = "\n\n【补充文献片段】：\n"
        MAX_CHUNK = 400
        for res in rag_results:
            text_part = res.get("text", "")
            rag_context += f"- {text_part[:MAX_CHUNK]}\n"

        # 定义苏格拉底式提问模板（融合RAG）
        socratic_template = PromptTemplate(
            input_variables=["paper_content", "reading_progress", "rag_context"],
            template="请作为一个学术导师，基于以下论文内容、阅读进度和补充的文献片段，生成5个苏格拉底式问题，帮助用户深入思考论文的核心内容。\n\n论文内容：\n{paper_content}\n\n用户阅读进度：\n{reading_progress}\n{rag_context}\n\n要求：\n1. 问题应该引导用户思考论文的核心假设、方法论、结果和意义\n2. 问题应该具有层次性，从理解基本概念到深入分析\n3. 问题应该鼓励用户批判性思考，而不是简单的事实回忆\n4. 每个问题都应该具体针对论文内容，避免过于宽泛\n\n生成的问题："
        )

        socratic_chain = LLMChain(llm=llm, prompt=socratic_template)
        questions_text = socratic_chain.run(
            paper_content=paper_content,
            reading_progress=reading_progress,
            rag_context=rag_context  # 传入RAG补充上下文
        )

        # 解析生成的问题
        questions = [q.strip() for q in questions_text.split('\n') if q.strip()]

        return JSONResponse({
            "status": "success",
            "questions": questions,
            "rag_sources": rag_results  # 可选：返回检索来源
        })

    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.post("/api/explain-term")
async def explain_term(request: TermExplainRequest):
    """动态术语解释功能（融合RAG检索 + Query Rewrite）"""

    try:
        term = request.term
        context = request.context

        # ===== 构造检索查询 =====
        rag_query = f"解释术语 '{term}' ，上下文：{context[:200]}"

        # ===== Query Rewrite =====
        rewrite_prompt = f"""
        You are helping a research retrieval system.

        Rewrite the following question into a concise academic search query.

        Focus on:
        - key technical terms
        - model names
        - research tasks

        Question:
        {rag_query}

        Search query:
       """

        try:
            rewritten_query = llm._call(rewrite_prompt).strip()
        except Exception:
            rewritten_query = rag_query

        print("Original Query:", rag_query)
        print("Rewritten Query:", rewritten_query)

        # ===== RAG检索 =====
        rag_results = hybrid.retrieve(rewritten_query)["vector"]

        print("RAG Results Count:", len(rag_results))

        # ===== 构造RAG上下文 =====
        rag_context = ""

        if rag_results:
            rag_context = "\n\nAdditional literature context:\n"

            MAX_CHUNK = 600
            for res in rag_results:
                text_part = res.get("text", "")
                rag_context += f"- {text_part[:MAX_CHUNK]}\n"

        # ===== Prompt模板 =====
        template = """
        You are an academic research assistant.

        Explain the technical term "{term}" using the context below.

        Requirements:
        1. Give a precise definition
        2. Explain how it is used in this paper
        3. Provide an example if possible
        4. Keep answer within 5 sentences
        5. Prefer information from the provided contexts

        Paper context:
        {context}

        Additional literature:
        {rag_context}

        Explanation:
        """
        term_explanation_template = PromptTemplate(
            input_variables=["term", "context", "rag_context"],
            template=template
        )

        term_explanation_chain = LLMChain(
            llm=llm,
            prompt=term_explanation_template
        )

        # ===== 生成解释 =====
        explanation = term_explanation_chain.run(
            term=term,
            context=context,
            rag_context=rag_context
        )

        return JSONResponse({
            "status": "success",
            "term": term,
            "explanation": explanation,
            "rag_sources": rag_results
        })

    except Exception as e:
        return JSONResponse({
            "status": "error",
            "message": str(e)
        }, status_code=500)


@app.post("/api/chat")
async def chat(request: ChatRequest):
    """简单 AI 对话：仅根据用户消息快速回复，不依赖 RAG/历史/论文上下文"""
    try:
        if not request.message or not request.message.strip():
            return JSONResponse(
                {"status": "error", "message": "消息不能为空"},
                status_code=400,
            )
        reply = llm._call(prompt=request.message.strip())
        return JSONResponse({
            "status": "success",
            "message": reply or "",
        })
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


# ===== 新增：RAG - 文献入库接口 =====
@app.post("/api/rag/add-literature")
async def rag_add_literature(file: UploadFile = File(...), metadata: dict = None):
    """
    将上传的文献解析后存入向量库
    :param file: PDF/Word格式的文献文件
    :param metadata: 文献元数据（可选，如{"title":"xxx", "author":"xxx"}）
    :return: 入库结果
    """
    try:
        # 1. 临时保存上传的文件
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as temp_file:
            content = await file.read()
            temp_file.write(content)
            temp_file_path = temp_file.name

        # 2. 调用RAG入库方法
        chunk_num = get_rag().add_literature_to_db(temp_file_path, metadata or {})

        # 3. 清理临时文件
        os.unlink(temp_file_path)

        return JSONResponse({
            "status": "success",
            "message": f"文献成功入库，生成{chunk_num}个向量片段",
            "chunk_num": chunk_num,
            "total_chunks": get_rag().get_db_stats()
        })
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


# ===== 新增：RAG - 相似片段检索接口 =====
@app.post("/api/rag/retrieve")
async def rag_retrieve(query: str, top_k: int = 5, filter_metadata: dict = None):
    """
    根据查询语句检索向量库中相似的文献片段
    :param query: 用户查询（如"这篇论文的核心贡献是什么？"）
    :param top_k: 召回Top-K个片段（默认5）
    :param filter_metadata: 元数据筛选（可选，如{"author":"张三"}）
    :return: 检索结果
    """
    try:
        results = hybrid.retrieve(query)

        return JSONResponse({
            "status": "success",
            "query": query,
            "results": results
        })
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@app.post("/api/deep-analysis")
async def deep_analysis(paper_content: str):
    """深度分析层：贡献与伪贡献识别"""
    # Step 1
    step1_prompt = f"""
    请从论文中提取作者声称的贡献点，列表形式返回。
    论文内容：
    {paper_content[:4000]}
    """

    claimed = llm._call(step1_prompt)

    # Step 2
    step2_prompt = f"""
    忽略作者自述，根据方法与实验内容推断论文真实贡献。
    论文内容：
    {paper_content[:4000]}
    """

    real = llm._call(step2_prompt)

    # Step 3
    step3_prompt = f"""
    对比以下两组内容：
    作者声明贡献：
    {claimed}

    推断真实贡献：
    {real}

    请指出：
    1. 是否存在夸大
    2. 是否存在伪创新
    3. 是否存在贡献重复包装
    """

    critique = llm._call(step3_prompt)

    return JSONResponse({
        "status": "success",
        "claimed_contributions": claimed,
        "inferred_real_contributions": real,
        "critical_analysis": critique
    })