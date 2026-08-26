"""
向量数据库服务 - 使用 Qdrant 实现研报的语义检索
"""
import os
import logging
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

logger = logging.getLogger(__name__)


class VectorDBService:
    """向量数据库服务"""

    def __init__(self, host: str = "localhost", port: int = 6333):
        """初始化向量数据库服务

        Args:
            host: Qdrant 服务器地址
            port: Qdrant 服务器端口
        """
        self.client = QdrantClient(host=host, port=port)
        self.collection_name = "research_reports"
        self.model_name = os.getenv("EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
        self._model = None
        self._vector_size: Optional[int] = None

        # 初始化集合
        self._init_collection()

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading embedding model: {self.model_name}")
            self._model = SentenceTransformer(self.model_name)
            self._vector_size = self._model.get_sentence_embedding_dimension()
        return self._model

    @property
    def vector_size(self) -> int:
        if self._vector_size is None:
            self._vector_size = self.model.get_sentence_embedding_dimension()
        return self._vector_size

    def _init_collection(self):
        """初始化向量集合"""
        try:
            # 检查集合是否存在
            collections = self.client.get_collections().collections
            exists = any(c.name == self.collection_name for c in collections)

            if not exists:
                logger.info(f"Creating collection: {self.collection_name}")
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=self.vector_size,
                        distance=Distance.COSINE
                    )
                )
                logger.info(f"Collection created: {self.collection_name}")
            else:
                logger.info(f"Collection already exists: {self.collection_name}")
        except Exception as e:
            logger.error(f"Failed to initialize collection: {e}")
            raise

    def add_report(self, report_id: str, title: str, content: str, metadata: Dict[str, Any]):
        """添加研报到向量数据库

        Args:
            report_id: 研报ID
            title: 研报标题
            content: 研报内容
            metadata: 元数据（作者、日期、公司等）
        """
        try:
            # 生成向量
            text = f"{title}\n{content}"
            vector = self.model.encode(text).tolist()

            # 添加到 Qdrant
            point = PointStruct(
                id=report_id,
                vector=vector,
                payload={
                    "title": title,
                    "content": content[:1000],  # 只存储前1000字符
                    **metadata
                }
            )

            self.client.upsert(
                collection_name=self.collection_name,
                points=[point]
            )
            logger.info(f"Added report to vector DB: {report_id}")
        except Exception as e:
            logger.error(f"Failed to add report {report_id}: {e}")
            raise

    def batch_add_reports(self, reports: List[Dict[str, Any]]):
        """批量添加研报

        Args:
            reports: 研报列表，每个包含 id, title, content, metadata
        """
        try:
            points = []
            for report in reports:
                text = f"{report['title']}\n{report['content']}"
                vector = self.model.encode(text).tolist()

                point = PointStruct(
                    id=report['id'],
                    vector=vector,
                    payload={
                        "title": report['title'],
                        "content": report['content'][:1000],
                        **report.get('metadata', {})
                    }
                )
                points.append(point)

            self.client.upsert(
                collection_name=self.collection_name,
                points=points
            )
            logger.info(f"Batch added {len(points)} reports to vector DB")
        except Exception as e:
            logger.error(f"Failed to batch add reports: {e}")
            raise

    def search_similar(self, query: str, top_k: int = 5, filter_dict: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """搜索相似研报

        Args:
            query: 查询文本
            top_k: 返回结果数量
            filter_dict: 过滤条件（如 {"manager_name": "张三"}）

        Returns:
            相似研报列表，包含 id, title, content, similarity, metadata
        """
        try:
            # 生成查询向量
            query_vector = self.model.encode(query).tolist()

            # 搜索。qdrant-client 1.17 使用 query_points，旧版本使用 search。
            if hasattr(self.client, "query_points"):
                response = self.client.query_points(
                    collection_name=self.collection_name,
                    query=query_vector,
                    limit=top_k,
                    query_filter=filter_dict,
                )
                results = response.points
            else:
                results = self.client.search(
                    collection_name=self.collection_name,
                    query_vector=query_vector,
                    limit=top_k,
                    query_filter=filter_dict,
                )

            # 格式化结果
            similar_reports = []
            for result in results:
                similar_reports.append({
                    "id": result.id,
                    "title": result.payload.get("title", ""),
                    "content": result.payload.get("content", ""),
                    "similarity": result.score,
                    "manager_name": result.payload.get("manager_name"),
                    "date": result.payload.get("date"),
                    "company": result.payload.get("company"),
                    "tags": result.payload.get("tags", [])
                })

            return similar_reports
        except Exception as e:
            logger.error(f"Failed to search similar reports: {e}")
            return []

    def delete_report(self, report_id: str):
        """删除研报

        Args:
            report_id: 研报ID
        """
        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=[report_id]
            )
            logger.info(f"Deleted report from vector DB: {report_id}")
        except Exception as e:
            logger.error(f"Failed to delete report {report_id}: {e}")
            raise

    def is_model_loaded(self) -> bool:
        """Return whether the embedding model has already been loaded."""
        return self._model is not None

    def warm_up(self) -> Dict[str, Any]:
        """Load the embedding model on demand and report warmup status."""
        model = self.model
        return {
            "model_loaded": True,
            "model_name": self.model_name,
            "vector_size": self.vector_size,
            "model_class": model.__class__.__name__,
        }

    def get_collection_info(self) -> Dict[str, Any]:
        """获取集合信息"""
        try:
            info = self.client.get_collection(collection_name=self.collection_name)
            return {
                "name": self.collection_name,
                "vectors_count": getattr(info, "vectors_count", getattr(info, "indexed_vectors_count", 0)),
                "points_count": getattr(info, "points_count", 0),
                "status": getattr(info, "status", None),
                "model_loaded": self.is_model_loaded(),
                "model_name": self.model_name,
                "vector_size": self._vector_size,
            }
        except Exception as e:
            logger.error(f"Failed to get collection info: {e}")
            return {
                "name": self.collection_name,
                "model_loaded": self.is_model_loaded(),
                "model_name": self.model_name,
                "vector_size": self._vector_size,
            }


# 全局实例
_vector_db_service: Optional[VectorDBService] = None


def get_vector_db() -> VectorDBService:
    """获取向量数据库服务实例"""
    global _vector_db_service
    if _vector_db_service is None:
        host = os.getenv("QDRANT_HOST", "localhost")
        port = int(os.getenv("QDRANT_PORT", "6333"))
        _vector_db_service = VectorDBService(host=host, port=port)
    return _vector_db_service
