# ai-service-python/main.py
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
import os
import tempfile
from grobid_client.grobid_client import GrobidClient
#from langchain_openai import ChatOpenAI
from langchain_community.chat_models import ChatDashScope
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
import json
from pydantic import BaseModel
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

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

app = FastAPI()

# 初始化GROBID客户端
grobid_client = GrobidClient(config_path=None, grobid_server="http://grobid:8070")

# 初始化LLM
#llm = ChatOpenAI(model_name="gpt-4o", temperature=0.3)
# 从环境变量中获取 API 密钥
api_key = os.environ.get("DASHSCOPE_API_KEY")
if not api_key:
    raise ValueError("请在 .env 文件中设置 DASHSCOPE_API_KEY 环境变量")
llm = ChatDashScope(model="qwen-max", temperature=0.3, dashscope_api_key=api_key)

# 定义摘要模板
summary_template = PromptTemplate(
    input_variables=["text", "section"],
    template="请对以下论文{section}部分进行简洁明了的总结，突出核心内容和关键信息：\n\n{text}\n\n总结："
)

summary_chain = LLMChain(llm=llm, prompt=summary_template)

@app.get("/")
def read_root():
    return {"message": "AI Paper Assistant Service is Running"}

@app.post("/api/deconstruct")
async def deconstruct_paper(file: UploadFile = File(...)):
    """自动化篇章解构功能"""
    try:
        # 保存上传的PDF文件
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_file:
            temp_file.write(await file.read())
            temp_file_path = temp_file.name
        
        # 使用GROBID解析PDF
        output_dir = tempfile.mkdtemp()
        grobid_client.process(
            "processFulltextDocument",
            input_path=temp_file_path,
            output=output_dir,
            consolidate_citations=True,
            tei_coordinates=True
        )
        
        # 读取解析结果
        tei_file = os.path.join(output_dir, os.path.basename(temp_file_path).replace(".pdf", ".tei.xml"))
        
        # 这里简化处理，实际应该解析TEI XML文件
        # 提取各个部分的文本
        sections = {
            "abstract": "摘要内容",
            "introduction": "引言内容",
            "methods": "方法内容",
            "results": "结果内容",
            "discussion": "讨论内容",
            "conclusion": "结论内容"
        }
        
        # 为每个部分生成摘要
        section_summaries = {}
        for section, text in sections.items():
            summary = summary_chain.run(text=text, section=section)
            section_summaries[section] = summary
        
        # 清理临时文件
        os.unlink(temp_file_path)
        for root, dirs, files in os.walk(output_dir):
            for file in files:
                os.unlink(os.path.join(root, file))
        os.rmdir(output_dir)
        
        # 返回结构化结果
        return JSONResponse({
            "status": "success",
            "sections": sections,
            "summaries": section_summaries,
            "paper_skeleton": {
                "abstract": section_summaries.get("abstract"),
                "introduction": section_summaries.get("introduction"),
                "methods": section_summaries.get("methods"),
                "results": section_summaries.get("results"),
                "discussion": section_summaries.get("discussion"),
                "conclusion": section_summaries.get("conclusion")
            }
        })
        
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

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
    """引导式学习引擎（苏格拉底式提问）"""
    try:
        paper_content = request.paper_content
        reading_progress = request.reading_progress
        
        # 定义苏格拉底式提问模板
        socratic_template = PromptTemplate(
            input_variables=["paper_content", "reading_progress"],
            template="请作为一个学术导师，基于以下论文内容和用户的阅读进度，生成5个苏格拉底式问题，帮助用户深入思考论文的核心内容。\n\n论文内容：\n{paper_content}\n\n用户阅读进度：\n{reading_progress}\n\n要求：\n1. 问题应该引导用户思考论文的核心假设、方法论、结果和意义\n2. 问题应该具有层次性，从理解基本概念到深入分析\n3. 问题应该鼓励用户批判性思考，而不是简单的事实回忆\n4. 每个问题都应该具体针对论文内容，避免过于宽泛\n\n生成的问题："
        )
        
        socratic_chain = LLMChain(llm=llm, prompt=socratic_template)
        questions_text = socratic_chain.run(paper_content=paper_content, reading_progress=reading_progress)
        
        # 解析生成的问题
        questions = [q.strip() for q in questions_text.split('\n') if q.strip()]
        
        return JSONResponse({
            "status": "success",
            "questions": questions
        })
        
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@app.post("/api/explain-term")
async def explain_term(request: TermExplainRequest):
    """动态术语解释功能"""
    try:
        term = request.term
        context = request.context
        
        # 定义术语解释模板
        term_explanation_template = PromptTemplate(
            input_variables=["term", "context"],
            template="请结合以下上下文，对术语 '{term}' 进行详细解释，包括：\n1. 该术语的基本定义\n2. 在本上下文中的具体含义\n3. 相关的应用案例或示例\n4. 与其他相关术语的区别\n\n上下文：\n{context}\n\n解释："
        )
        
        term_explanation_chain = LLMChain(llm=llm, prompt=term_explanation_template)
        explanation = term_explanation_chain.run(term=term, context=context)
        
        return JSONResponse({
            "status": "success",
            "term": term,
            "explanation": explanation
        })
        
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)