"""
调研报告搜索服务 - 语义检索
"""
import os
import logging
from typing import Dict, Any, List, Optional, Tuple
import hashlib

logger = logging.getLogger(__name__)

# Embedding API - 使用 OpenAI-compatible 或本地模型
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_EMBEDDING_URL = os.environ.get("OPENAI_EMBEDDING_URL", "https://api.openai.com/v1/embeddings")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")


def compute_text_hash(text: str) -> str:
    """计算文本哈希，用于去重"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """计算两个向量的余弦相似度"""
    if len(a) != len(b):
        return 0.0
    dot_product = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot_product / (norm_a * norm_b)


class EmbeddingService:
    """文本向量化服务"""

    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None and OPENAI_API_KEY:
            try:
                import openai
                self._client = openai.OpenAI(api_key=OPENAI_API_KEY)
            except ImportError:
                try:
                    from openai import OpenAI
                    self._client = OpenAI(api_key=OPENAI_API_KEY)
                except ImportError:
                    logger.warning("OpenAI SDK not available")
        return self._client

    def get_embedding(self, text: str) -> Optional[List[float]]:
        """获取文本的向量表示"""
        if not self.client:
            logger.warning("Embedding API key/client unavailable; semantic embedding is disabled")
            return None

        try:
            response = self.client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=text[:8000],  # 限制文本长度
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Embedding API error: {e}")
            return None


class ResearchReportSearch:
    """调研报告语义搜索"""

    def __init__(self, embedding_service: EmbeddingService = None):
        self.embedding_service = embedding_service or EmbeddingService()

    def compute_report_embedding(self, report: Dict[str, Any]) -> Optional[List[float]]:
        """计算报告的向量表示"""
        # 使用标题 + 摘要 + 要点生成向量
        text_parts = [
            report.get("title", ""),
            report.get("summary", ""),
            report.get("content", "")[:2000],
        ]
        combined_text = " | ".join(filter(None, text_parts))
        return self.embedding_service.get_embedding(combined_text)

    def search_similar(
        self,
        reports: List[Dict[str, Any]],
        query: str,
        top_k: int = 5,
        min_similarity: float = 0.3,
    ) -> List[Tuple[Dict[str, Any], float]]:
        """
        在报告列表中搜索与query最相似的报告
        返回: [(report, similarity_score), ...]
        """
        query_embedding = self.embedding_service.get_embedding(query)
        if query_embedding is None:
            logger.warning("Semantic search unavailable; falling back to keyword search only")
            keywords = [item for item in query.split() if item]
            return [(report, 1.0) for report in self.keyword_search(reports, keywords)[:top_k]]
        scored_reports = []

        for report in reports:
            # 获取报告向量（如果有的话）
            stored_embedding = report.get("embedding")
            if stored_embedding and isinstance(stored_embedding, list):
                sim = cosine_similarity(query_embedding, stored_embedding)
            else:
                # 实时计算（存储时应该已计算）
                computed = self.compute_report_embedding(report)
                if computed is None:
                    continue
                sim = cosine_similarity(query_embedding, computed)

            if sim >= min_similarity:
                scored_reports.append((report, round(sim, 4)))

        scored_reports.sort(key=lambda x: x[1], reverse=True)
        return scored_reports[:top_k]

    def keyword_search(
        self,
        reports: List[Dict[str, Any]],
        keywords: List[str],
    ) -> List[Dict[str, Any]]:
        """基于关键词搜索报告"""
        results = []
        for report in reports:
            content = f"{report.get('title', '')} {report.get('summary', '')} {report.get('content', '')}"
            content_lower = content.lower()
            matched = [kw for kw in keywords if kw.lower() in content_lower]
            if matched:
                results.append({
                    **report,
                    "matched_keywords": matched,
                    "match_count": len(matched),
                })
        return sorted(results, key=lambda x: x["match_count"], reverse=True)


# 全局单例
_embedding_service: Optional[EmbeddingService] = None
_search_service: Optional[ResearchReportSearch] = None


def get_embedding_service() -> EmbeddingService:
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service


def get_search_service() -> ResearchReportSearch:
    global _search_service
    if _search_service is None:
        _search_service = ResearchReportSearch(get_embedding_service())
    return _search_service
