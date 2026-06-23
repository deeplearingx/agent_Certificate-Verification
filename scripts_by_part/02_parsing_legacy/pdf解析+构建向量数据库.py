
import json
import time
import re
import json
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime

from llama_index.core.schema import TextNode
import chromadb
from pathlib import Path
from typing import List, Dict

import chromadb
from llama_index.core import VectorStoreIndex, StorageContext, Settings, get_response_synthesizer
from llama_index.core.schema import TextNode
from llama_index.llms.huggingface import HuggingFaceLLM
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.chroma import ChromaVectorStore
from llama_index.core import PromptTemplate
from llama_index.core.postprocessor import SentenceTransformerRerank  # 新增重排序组件
from llama_index.llms.openai_like import OpenAILike

# QA_TEMPLATE = (
#     "<|im_start|>system\n"
#     "您是中国劳动法领域专业助手，必须严格遵循以下规则：\n"
#     "1.仅使用提供的法律条文回答问题\n"
#     "2.若问题与劳动法无关或超出知识库范围，明确告知无法回答\n"
#     "3.引用条文时标注出处\n\n"
#     "可用法律条文（共{context_count}条）：\n{context_str}\n<|im_end|>\n"
#     "<|im_start|>user\n问题：{query_str}<|im_end|>\n"
#     "<|im_start|>assistant\n"
# )


# response_template = PromptTemplate(QA_TEMPLATE)

# ================== 配置区 ==================
class Config:
    EMBED_MODEL_PATH = r"D:\workspace\ai_learning\pythonProject\models\BAAI\bge-m3"
    RERANK_MODEL_PATH = r"D:\workspace\ai_learning\pythonProject\models\BAAI\bge-reranker-large"  # 新增重排序模型路径
    LLM_MODEL_PATH = r"/home/cw/llms/Qwen/Qwen1___5-1___8B-Chat"
    
    DATA_DIR = "./data"
    VECTOR_DB_DIR = "./chroma_db"
    PERSIST_DIR = "./storage"
    
    COLLECTION_NAME = "chinese_labor_laws"
    TOP_K = 10  # 扩大初始检索数量
    RERANK_TOP_K = 3  # 重排序后保留数量

# ================== 初始化模型 ==================
def init_models():
    """初始化模型并验证"""
    # Embedding模型
    embed_model = HuggingFaceEmbedding(
        model_name=Config.EMBED_MODEL_PATH,
    )
    
    # LLM
    # llm = HuggingFaceLLM(
    #     model_name=Config.LLM_MODEL_PATH,
    #     tokenizer_name=Config.LLM_MODEL_PATH,
    #     model_kwargs={
    #         "trust_remote_code": True,
    #     },
    #     tokenizer_kwargs={"trust_remote_code": True},
    #     generate_kwargs={"temperature": 0.3}
    # )

    #openai_like
    llm = OpenAILike(
        model="deepseek-chat",  # 可选模型：glm-4, glm-3-turbo, characterglm等
        api_base="https://api.deepseek.com/v1",  # 关键！必须指定此端点
        api_key="",
        context_window=128000,    # 按需调整（glm-4实际支持128K）
        is_chat_model=True,
        is_function_calling_model=False,  # GLM暂不支持函数调用
        max_tokens=1024,          # 最大生成token数（按需调整）
        temperature=0.3,          # 推荐范围 0.1~1.0
        top_p=0.7                 # 推荐范围 0.5~1.0
    )
    
    # 初始化重排序器（新增）
    reranker = SentenceTransformerRerank(
        model=Config.RERANK_MODEL_PATH,
        top_n=Config.RERANK_TOP_K
    )
    
    Settings.embed_model = embed_model
    Settings.llm = llm
    
    # 验证模型
    test_embedding = embed_model.get_text_embedding("测试文本")
    print(f"Embedding维度验证：{len(test_embedding)}")
    
    return embed_model, llm, reranker  # 返回重排序器

# ================== 数据处理 ==================
def load_and_validate_json_files(data_dir: str) -> List[Dict]:
    """加载并验证JSON法律文件"""
    json_files = list(Path(data_dir).glob("*.json"))
    assert json_files, f"未找到JSON文件于 {data_dir}"
    
    all_data = []
    for json_file in json_files:
        with open(json_file, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
                # 验证数据结构
                if not isinstance(data, list):
                    raise ValueError(f"文件 {json_file.name} 根元素应为列表")
                for item in data:
                    if not isinstance(item, dict):
                        raise ValueError(f"文件 {json_file.name} 包含非字典元素")
                    for k, v in item.items():
                        if not isinstance(v, str):
                            raise ValueError(f"文件 {json_file.name} 中键 '{k}' 的值不是字符串")
                all_data.extend({
                    "content": item,
                    "metadata": {"source": json_file.name}
                } for item in data)
            except Exception as e:
                raise RuntimeError(f"加载文件 {json_file} 失败: {str(e)}")
    
    print(f"成功加载 {len(all_data)} 个法律文件条目")
    return all_data

def create_nodes(raw_data: List[Dict]) -> List[TextNode]:
    """添加ID稳定性保障"""
    nodes = []
    for entry in raw_data:
        law_dict = entry["content"]
        source_file = entry["metadata"]["source"]
        
        for full_title, content in law_dict.items():
            # 生成稳定ID（避免重复）
            node_id = f"{source_file}::{full_title}"
            
            parts = full_title.split(" ", 1)
            law_name = parts[0] if len(parts) > 0 else "未知法律"
            article = parts[1] if len(parts) > 1 else "未知条款"
            
            node = TextNode(
                text=content,
                id_=node_id,  # 显式设置稳定ID
                metadata={
                    "law_name": law_name,
                    "article": article,
                    "full_title": full_title,
                    "source_file": source_file,
                    "content_type": "legal_article"
                }
            )
            nodes.append(node)
    
    print(f"生成 {len(nodes)} 个文本节点（ID示例：{nodes[0].id_}）")
    return nodes

# ================== 向量存储 ==================

# def init_vector_store(nodes: List[TextNode]) -> VectorStoreIndex:
#     chroma_client = chromadb.PersistentClient(path=Config.VECTOR_DB_DIR)
#     chroma_collection = chroma_client.get_or_create_collection(
#         name=Config.COLLECTION_NAME,
#         metadata={"hnsw:space": "cosine"}
#     )
#
#     # 确保存储上下文正确初始化
#     storage_context = StorageContext.from_defaults(
#         vector_store=ChromaVectorStore(chroma_collection=chroma_collection)
#     )
#
#     # 判断是否需要新建索引
#     if chroma_collection.count() == 0 and nodes is not None:
#         print(f"创建新索引（{len(nodes)}个节点）...")
#
#         # 显式将节点添加到存储上下文
#         storage_context.docstore.add_documents(nodes)
#
#         index = VectorStoreIndex(
#             nodes,
#             storage_context=storage_context,
#             show_progress=True
#         )
#         # 双重持久化保障
#         storage_context.persist(persist_dir=Config.PERSIST_DIR)
#         index.storage_context.persist(persist_dir=Config.PERSIST_DIR)  # <-- 新增
#     else:
#         print("加载已有索引...")
#         storage_context = StorageContext.from_defaults(
#             persist_dir=Config.PERSIST_DIR,
#             vector_store=ChromaVectorStore(chroma_collection=chroma_collection)
#         )
#         index = VectorStoreIndex.from_vector_store(
#             storage_context.vector_store,
#             storage_context=storage_context,
#             embed_model=Settings.embed_model
#         )
#
#     # 安全验证
#     print("\n存储验证结果：")
#     doc_count = len(storage_context.docstore.docs)
#     print(f"DocStore记录数：{doc_count}")
#
#     if doc_count > 0:
#         sample_key = next(iter(storage_context.docstore.docs.keys()))
#         print(f"示例节点ID：{sample_key}")
#     else:
#         print("警告：文档存储为空，请检查节点添加逻辑！")
#
#
#     return index


def init_vector_store() -> VectorStoreIndex:  # 不再接收 nodes 作为参数
    chroma_client = chromadb.PersistentClient(path=Config.VECTOR_DB_DIR)
    chroma_collection = chroma_client.get_or_create_collection(
        name=Config.COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}
    )

    storage_context = StorageContext.from_defaults(
        vector_store=ChromaVectorStore(chroma_collection=chroma_collection)
    )

    # 核心判断逻辑：如果集合为空，则加载数据并构建索引
    if chroma_collection.count() == 0:
        print("数据库集合为空，开始加载数据并创建新索引...")

        # 将数据加载逻辑移到这里
        raw_data = load_and_validate_json_files(Config.DATA_DIR)
        nodes = create_nodes(raw_data)

        if not nodes:
            raise RuntimeError("未能从数据源创建任何节点，无法构建索引。")

        index = VectorStoreIndex(
            nodes,
            storage_context=storage_context,
            show_progress=True
        )
        # 持久化
        index.storage_context.persist(persist_dir=Config.PERSIST_DIR)
    else:
        print(f"加载已有索引（包含 {chroma_collection.count()} 个文档）...")
        # LlamaIndex 从 0.10.x 版本开始，推荐直接从 VectorStore 加载
        index = VectorStoreIndex.from_vector_store(
            vector_store=storage_context.vector_store,
            embed_model=Settings.embed_model
        )

    # 验证部分可以保留
    print("\n存储验证结果：")
    doc_count_in_store = chroma_collection.count()
    print(f"ChromaDB集合中的文档数：{doc_count_in_store}")

    if doc_count_in_store == 0:
        print("警告：索引初始化后，数据库中仍然没有文档！")

    return index

#新增过滤函数
def is_legal_question(text: str) -> bool:
    """判断问题是否属于法律咨询"""
    legal_keywords = ["劳动法", "合同", "工资", "工伤", "解除", "赔偿"]
    return any(keyword in text for keyword in legal_keywords)

# ================== 主程序 ==================
def main():
    embed_model, llm, reranker = init_models()  # 获取重排序器
    
    # # 仅当需要更新数据时执行
    # if not Path(Config.VECTOR_DB_DIR).exists():
    #     print("\n初始化数据...")
    #     raw_data = load_and_validate_json_files(Config.DATA_DIR)
    #     nodes = create_nodes(raw_data)
    # else:
    #     nodes = None

    # print("\n初始化向量存储...")
    # start_time = time.time()
    # index = init_vector_store(nodes)
    # print(f"索引加载耗时：{time.time()-start_time:.2f}s")


    print("\n初始化向量存储...")
    start_time = time.time()
    # 直接调用修改后的函数
    index = init_vector_store()
    print(f"索引加载耗时：{time.time()-start_time:.2f}s")


    # 创建检索器和响应合成器（修改部分）
    retriever = index.as_retriever(
        similarity_top_k=Config.TOP_K  # 扩大初始检索数量
    )
    response_synthesizer = get_response_synthesizer(
        # text_qa_template=response_template,
        verbose=True
    )
    
    # 示例查询
    while True:
        question = input("\n请输入劳动法相关问题（输入q退出）: ")
        if question.lower() == 'q':
            break
        # 添加问答类型判断（关键修改）
        # if not is_legal_question(question):  # 新增判断函数
        #     print("\n您好！我是劳动法咨询助手，专注解答《劳动法》《劳动合同法》等相关问题。")
        #     continue
       # 执行检索-重排序-过滤-回答流程
        start_time = time.time()
        
        # 1. 初始检索
        initial_nodes = retriever.retrieve(question)
        retrieval_time = time.time() - start_time
        
        # 2. 重排序
        reranked_nodes = reranker.postprocess_nodes(
            initial_nodes, 
            query_str=question
        )
        rerank_time = time.time() - start_time - retrieval_time

        
        # ★★★★★ 添加过滤逻辑在此处 ★★★★★
        
        MIN_RERANK_SCORE = 0.4
        
        # 执行过滤
        filtered_nodes = [
            node for node in reranked_nodes 
            if node.score > MIN_RERANK_SCORE
        ]
        # for node in reranked_nodes:
        #     print(node.score)
        #一般对模型的回复做限制就从filtered_nodes的返回值下手
        print("原始分数样例：",[node.score for node in reranked_nodes[:3]])
        print("重排序过滤后的结果：",filtered_nodes)
        # 空结果处理
        if not filtered_nodes:
            print("你的问题未匹配到相关资料！")
            continue
        # 3. 合成答案（使用过滤后的节点）
        response = response_synthesizer.synthesize(
            question, 
            nodes=filtered_nodes  # 使用过滤后的节点
        )
        synthesis_time = time.time() - start_time - retrieval_time - rerank_time
        
        # 显示结果（修改显示逻辑）
        print(f"\n智能助手回答：\n{response.response}")
        print("\n支持依据：")
        for idx, node in enumerate(reranked_nodes, 1):
            # 兼容新版API的分数获取方式
            initial_score = node.metadata.get('initial_score', node.score)  # 获取初始分数
            rerank_score = node.score  # 重排序后的分数
        
            meta = node.node.metadata
            print(f"\n[{idx}] {meta['full_title']}")
            print(f"  来源文件：{meta['source_file']}")
            print(f"  法律名称：{meta['law_name']}")
            print(f"  初始相关度：{node.node.metadata.get('initial_score', 0):.4f}")  # 安全访问
            print(f"  重排序得分：{getattr(node, 'score', 0):.4f}")  # 兼容属性访问
            print(f"  条款内容：{node.node.text[:100]}...")
        
        print(f"\n[性能分析] 检索: {retrieval_time:.2f}s | 重排序: {rerank_time:.2f}s | 合成: {synthesis_time:.2f}s")

if __name__ == "__main__":
    main()
