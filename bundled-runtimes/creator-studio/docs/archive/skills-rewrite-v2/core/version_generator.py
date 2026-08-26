#!/usr/bin/env python3
"""
VersionGenerator: 改写版本生成引擎

功能: 基于配置化的版本schema，并行生成多个平台/tone的版本
支持: 自定义版本定义、动态版本扩展
"""

import json
import asyncio
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor


@dataclass
class GenerationTask:
    """版本生成任务"""
    version_id: str
    platform: str
    tone: str
    original_doc: str
    final_snapshot: Dict
    prompt_builder: object
    model: str = "claude-opus-4-6"


class VersionGenerator:
    """
    版本生成引擎

    使用方式:
        generator = VersionGenerator(config_file="version_schemas.json")
        results = generator.generate_all_versions(
            original_doc=initial_draft,
            final_snapshot=structure_snapshot,
            max_workers=4
        )
    """

    def __init__(self, config_file: str = None):
        """
        初始化生成器

        Args:
            config_file: version_schemas.json 配置文件路径
        """
        if config_file is None:
            config_file = str(
                Path(__file__).parent.parent / "templates" / "configs" / "version_schemas.json"
            )

        with open(config_file, 'r', encoding='utf-8') as f:
            self.config = json.load(f)

        self.version_schemas = {v["id"]: v for v in self.config["version_definitions"]}
        self.platform_defs = {p["platform"]: p for p in self.config["platform_definitions"]}
        self.tone_defs = {t["tone"]: t for t in self.config["tone_definitions"]}

        # Add alias support for common abbreviations
        self.version_aliases = {
            "xhs_hot": "xiaohongshu_hot",
            "xhs_normal": "xiaohongshu_normal",
            "wechat_luxun_hot": "wechat_hot",  # Legacy alias
            "wechat_lemon_normal": "wechat_normal",  # Legacy alias
            "xhs_luxun_hot": "xiaohongshu_hot",  # Legacy alias
            "xhs_lemon_normal": "xiaohongshu_normal",  # Legacy alias
        }

    def get_version_schema(self, version_id: str) -> Dict:
        """
        获取特定版本的schema

        Args:
            version_id: 版本ID (如 "wechat_hot" 或 "xhs_hot")

        Returns:
            版本schema配置
        """
        # Check if it's an alias first
        if version_id in self.version_aliases:
            version_id = self.version_aliases[version_id]

        if version_id not in self.version_schemas:
            raise ValueError(f"Unknown version: {version_id}")
        return self.version_schemas[version_id]

    def get_all_versions(self) -> List[str]:
        """
        获取所有可用版本列表

        Returns:
            版本ID列表
        """
        return list(self.version_schemas.keys())

    def get_versions_by_platform(self, platform: str) -> List[str]:
        """
        获取特定平台的所有版本

        Args:
            platform: 平台名称

        Returns:
            该平台的版本ID列表
        """
        return [v for v in self.version_schemas.keys() if self.version_schemas[v]["platform"] == platform]

    def get_versions_by_tone(self, tone: str) -> List[str]:
        """
        获取特定语气的所有版本

        Args:
            tone: 语气名称

        Returns:
            该语气的版本ID列表
        """
        return [v for v in self.version_schemas.keys() if self.version_schemas[v]["tone"] == tone]

    def generate_versions(
        self,
        version_ids: List[str],
        original_doc: str,
        final_snapshot: Dict,
        max_workers: int = 4
    ) -> Dict[str, Dict]:
        """
        并行生成多个版本

        Args:
            version_ids: 要生成的版本ID列表
            original_doc: 原始初稿
            final_snapshot: 最终结构快照
            max_workers: 并发数

        Returns:
            {版本ID: 生成结果}
        """
        results = {}

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for version_id in version_ids:
                future = executor.submit(
                    self._generate_single_version,
                    version_id,
                    original_doc,
                    final_snapshot
                )
                futures[version_id] = future

            for version_id, future in futures.items():
                try:
                    result = future.result(timeout=300)  # 5分钟超时
                    results[version_id] = result
                except Exception as e:
                    results[version_id] = {"error": str(e), "status": "failed"}

        return results

    def generate_all_versions(
        self,
        original_doc: str,
        final_snapshot: Dict,
        max_workers: int = 4
    ) -> Dict[str, Dict]:
        """
        生成所有版本

        Args:
            original_doc: 原始初稿
            final_snapshot: 最终结构快照
            max_workers: 并发数

        Returns:
            所有版本的生成结果
        """
        all_versions = self.get_all_versions()
        return self.generate_versions(all_versions, original_doc, final_snapshot, max_workers)

    def generate_platform_versions(
        self,
        platform: str,
        original_doc: str,
        final_snapshot: Dict,
        max_workers: int = 4
    ) -> Dict[str, Dict]:
        """
        生成特定平台的所有版本

        Args:
            platform: 平台名称
            original_doc: 原始初稿
            final_snapshot: 最终结构快照
            max_workers: 并发数

        Returns:
            该平台所有版本的生成结果
        """
        versions = self.get_versions_by_platform(platform)
        return self.generate_versions(versions, original_doc, final_snapshot, max_workers)

    def _generate_single_version(
        self,
        version_id: str,
        original_doc: str,
        final_snapshot: Dict
    ) -> Dict:
        """
        生成单个版本（内部方法）

        Args:
            version_id: 版本ID
            original_doc: 原始初稿
            final_snapshot: 最终结构快照

        Returns:
            生成结果
        """
        schema = self.get_version_schema(version_id)

        try:
            # 这里应该调用Claude API进行实际改写
            # 为了演示，这里返回元数据
            result = {
                "version_id": version_id,
                "platform": schema["platform"],
                "tone": schema["tone"],
                "name": schema["name"],
                "status": "pending",  # 实际应该是 "generating" -> "completed" 或 "failed"
                "config": {
                    "word_count_target": schema.get("word_count", {}).get("target"),
                    "quality_threshold": schema.get("quality_threshold"),
                },
                "timestamp": self._get_timestamp()
            }

            return result

        except Exception as e:
            return {
                "version_id": version_id,
                "status": "failed",
                "error": str(e)
            }

    def get_generation_config(self, version_id: str) -> Dict:
        """
        获取版本生成的配置信息（用于Prompt构建）

        Args:
            version_id: 版本ID

        Returns:
            包含所有约束条件的配置字典
        """
        schema = self.get_version_schema(version_id)
        platform_def = self.platform_defs[schema["platform"]]
        tone_def = self.tone_defs[schema["tone"]]

        return {
            "version": schema,
            "platform": platform_def,
            "tone": tone_def,
            "constraints": self._extract_constraints(schema),
            "requirements": self._extract_requirements(schema)
        }

    @staticmethod
    def _extract_constraints(schema: Dict) -> Dict:
        """
        从schema提取约束条件
        """
        constraints = {}

        if "word_count" in schema:
            constraints["word_count"] = schema["word_count"]

        if "required_anchors" in schema:
            constraints["required_anchors"] = schema["required_anchors"]

        if "paragraph_length" in schema:
            constraints["paragraph_length"] = schema["paragraph_length"]

        if "emoji_count" in schema:
            constraints["emoji_count"] = schema["emoji_count"]

        if "hashtag_count" in schema:
            constraints["hashtag_count"] = schema["hashtag_count"]

        return constraints

    @staticmethod
    def _extract_requirements(schema: Dict) -> List[str]:
        """
        从schema提取需求列表
        """
        requirements = []

        if schema.get("hook_requirement"):
            requirements.append(f"开篇必须包含Hook（位置：{schema.get('hook_position', 'start')}）")

        if schema.get("call_to_action"):
            requirements.append(f"结尾包含行动呼吁：{schema['call_to_action']}")

        if schema.get("image_count_min"):
            requirements.append(f"至少{schema['image_count_min']}张配图")

        if "title_requirements" in schema:
            requirements.append(f"标题长度：{schema['title_requirements'].get('min_length', '')}-{schema['title_requirements'].get('max_length', '')}字")

        if schema.get("tone_style"):
            requirements.append(f"语气风格：{schema['tone_style']}")

        return requirements

    @staticmethod
    def _get_timestamp() -> str:
        from datetime import datetime
        return datetime.now().isoformat()


if __name__ == "__main__":
    # 示例使用
    generator = VersionGenerator()

    print("="*70)
    print("版本生成引擎 - 配置演示")
    print("="*70)

    # 列出所有版本
    all_versions = generator.get_all_versions()
    print(f"\n已配置的版本 ({len(all_versions)}):")
    for vid in all_versions:
        schema = generator.get_version_schema(vid)
        print(f"  - {vid}: {schema['name']} ({schema['word_count']['target']}字)")

    # 按平台分组
    print(f"\n按平台分组:")
    for platform_id in ["wechat", "xiaohongshu", "douyin"]:
        versions = generator.get_versions_by_platform(platform_id)
        if versions:
            print(f"  {platform_id}: {', '.join(versions)}")

    # 获取某个版本的完整配置
    print(f"\n版本 'wechat_hot' 的完整配置:")
    config = generator.get_generation_config("wechat_hot")
    print(f"  字数目标: {config['constraints']['word_count']['target']} (范围: {config['constraints']['word_count']['min']}-{config['constraints']['word_count']['max']})")
    print(f"  质量阈值: {config['version']['quality_threshold']}/10")
    print(f"  关键需求:")
    for req in config['requirements'][:3]:
        print(f"    - {req}")

    print(f"\n" + "="*70)
