#!/usr/bin/env python3
"""
Rewrite Stage 5 执行脚本

执行流程:
1. 加载初稿文件
2. 使用PromptBuilder为每个版本生成改写prompt
3. 调用Claude API执行改写
4. 使用QualityScorer评分
5. 使用AnchorMapper检查锚点保留
6. 生成manifest和报告
7. 同步到飞书
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime

# 添加skills路径
skills_path = Path(__file__).parent.parent / "skills" / "dasheng-media-rewrite-v2"
sys.path.insert(0, str(skills_path))

from core.enhanced_prompt_builder import EnhancedPromptBuilder
from core.quality_scorer import QualityScorer
from core.anchor_mapper import AnchorMapper
from core.version_generator import VersionGenerator

# 默认版本
DEFAULT_VERSIONS = [
    "wechat_hot",
    "wechat_normal",
    "xiaohongshu_hot",
    "xiaohongshu_normal"
]

class RewriteExecutor:
    def __init__(self, draft_manifest_file: Path, output_dir: Path, run_id: str, versions: list[str], timeout: int = 120):
        import anthropic

        self.client = anthropic.Anthropic()
        self.timeout = timeout
        self.generator = VersionGenerator()
        self.draft_manifest_file = draft_manifest_file
        self.output_dir = output_dir
        self.run_id = run_id
        self.versions = versions
        self.results = {
            "run_id": run_id,
            "timestamp": datetime.now().isoformat(),
            "topics": {},
            "summary": {}
        }

        # 加载draft manifest
        self.draft_manifest = json.loads(draft_manifest_file.read_text(encoding='utf-8'))
        self.draft_dir = Path(self.draft_manifest.get("output_dir", draft_manifest_file.parent))

    def load_draft(self, topic_id: str) -> str:
        """加载初稿文件"""
        # 从manifest中查找对应的draft_file路径
        for draft_item in self.draft_manifest.get("drafts", []):
            if draft_item.get("topic_id") == topic_id:
                draft_file = Path(draft_item.get("draft_file", ""))
                if draft_file.exists():
                    return draft_file.read_text(encoding='utf-8')
                else:
                    raise FileNotFoundError(f"Draft file not found: {draft_file}")

        # 如果manifest中没有找到，尝试旧的命名方式（兼容性）
        draft_file = self.draft_dir / f"03_标准初稿_{topic_id}.md"
        if not draft_file.exists():
            raise FileNotFoundError(f"Draft file not found in manifest or directory: {topic_id}")
        return draft_file.read_text(encoding='utf-8')

    def generate_rewrite_prompt(self, version_id: str, original_text: str) -> str:
        """生成增强版改写prompt"""
        schema = self.generator.get_version_schema(version_id)
        platform = schema["platform"]
        tone = schema["tone"]

        # 使用增强版Prompt构建器
        builder = EnhancedPromptBuilder()
        platform_name = {"wechat": "微信公众号", "xiaohongshu": "小红书", "douyin": "抖音"}[platform]
        tone_name = {"hot": "热点版", "normal": "常规版"}[tone]

        prompt = builder.build_enhanced_prompt(
            platform=platform_name,
            tone=tone_name,
            original_text=original_text,
            target_word_count=schema["word_count"]["target"],
            min_word_count=schema["word_count"]["min"],
            max_word_count=schema["word_count"]["max"],
            primary_audience=schema.get("primary_audience", "")
        )

        return prompt

    def call_claude(self, prompt: str, timeout: int = None) -> str:
        """调用Claude API"""
        # 使用system参数明确角色，避免身份冲突
        effective_timeout = timeout if timeout is not None else self.timeout
        message = self.client.messages.create(
            model="claude-opus-4-6",
            max_tokens=4096,
            timeout=effective_timeout,
            system="你是一位专业的内容改写专家，擅长将文章改写为不同平台和语气的版本。请严格按照用户提供的改写规则执行，直接输出改写后的完整文稿，不要包含任何解释或元评论。",
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        return message.content[0].text

    def should_regenerate(self, version_result: dict) -> bool:
        """判断是否需要重新生成"""
        if version_result.get("status") != "completed":
            return True

        # 质量评分低于8.0需要重新生成（Rewrite阶段标准）
        if version_result.get("quality_score", 0) < 8.0:
            return True

        # 字数偏差超过15%需要重新生成（从30%收紧到15%）
        word_count = version_result.get("word_count", 0)
        target = version_result.get("target_word_count", 1000)
        deviation = abs(word_count - target) / target
        if deviation > 0.15:
            return True

        # 锚点保留率低于80%需要重新生成
        if version_result.get("anchor_preserved_rate", 0) < 80:
            return True

        return False

    def execute_rewrite(self, topic: str) -> dict:
        """为一个主题执行所有版本的改写"""
        print(f"\n{'='*70}")
        print(f"处理主题: {topic}")
        print(f"{'='*70}")

        try:
            # 加载初稿
            original_draft = self.load_draft(topic)
            topic_results = {}

            # 为每个版本执行改写（带重试机制）
            MAX_RETRIES = 3
            for version_id in self.versions:
                print(f"\n→ 生成{version_id}版本...")

                best_result = None
                best_score = 0

                for attempt in range(1, MAX_RETRIES + 1):
                    try:
                        if attempt > 1:
                            print(f"  ⟳ 第{attempt}次尝试（质量未达标，重新生成）...")

                        # 生成prompt
                        prompt = self.generate_rewrite_prompt(version_id, original_draft)

                        # 调用Claude
                        rewritten_text = self.call_claude(prompt)

                        # 运行质量评分
                        schema = self.generator.get_version_schema(version_id)
                        scorer = QualityScorer(
                            platform=schema["platform"],
                            tone=schema["tone"],
                            original_doc=original_draft,
                            final_snapshot={"sections": []}
                        )
                        quality_report = scorer.score(rewritten_text)

                        # 运行锚点映射
                        anchor_mapper = AnchorMapper(original_draft, rewritten_text)
                        anchor_report = anchor_mapper.generate_report()

                        # 构建结果
                        result = {
                            "status": "completed",
                            "content": rewritten_text,
                            "quality_score": quality_report.overall_score,
                            "quality_status": quality_report.status,
                            "anchor_preserved_rate": anchor_report.preserved_rate,
                            "word_count": len(rewritten_text),
                            "target_word_count": schema["word_count"]["target"],
                            "attempt": attempt
                        }

                        print(f"  ✓ 质量评分: {quality_report.overall_score}/10 ({quality_report.status})")
                        print(f"  ✓ 锚点保留率: {anchor_report.preserved_rate}%")
                        print(f"  ✓ 字数: {len(rewritten_text)} (目标: {schema['word_count']['target']})")

                        # 保存最佳结果
                        if quality_report.overall_score > best_score:
                            best_result = result
                            best_score = quality_report.overall_score

                        # 检查是否需要重新生成
                        if not self.should_regenerate(result):
                            print(f"  ✓ 质量达标，使用此版本")
                            topic_results[version_id] = result
                            break
                        else:
                            if attempt < MAX_RETRIES:
                                print(f"  ⚠ 质量未达标（分数<8.0 或 字数偏差>15% 或 锚点<80%）")
                            else:
                                print(f"  ⚠ 已达最大重试次数，使用最佳版本（分数: {best_score}/10）")
                                topic_results[version_id] = best_result

                    except Exception as e:
                        print(f"  ✗ 第{attempt}次尝试失败: {str(e)}")
                        if attempt == MAX_RETRIES:
                            topic_results[version_id] = {
                                "status": "failed",
                                "error": str(e),
                                "attempts": attempt
                            }

            self.results["topics"][topic] = topic_results
            return topic_results

        except Exception as e:
            print(f"✗ 主题处理失败: {str(e)}")
            self.results["topics"][topic] = {"status": "failed", "error": str(e)}
            return {}

    def execute_all(self):
        """执行所有主题的改写"""
        print("\n🚀 启动Rewrite Stage 5 执行")
        print(f"Run ID: {self.run_id}")

        # 从draft manifest获取主题列表
        topics = []
        for draft_item in self.draft_manifest.get("drafts", []):
            topic_id = draft_item.get("topic_id", "")
            if topic_id:
                topics.append(topic_id)

        print(f"主题数: {len(topics)}")
        print(f"版本数: {len(self.versions)}")
        print(f"总任务数: {len(topics) * len(self.versions)}")

        # 创建输出目录
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 执行每个主题
        completed = 0
        failed = 0

        for topic in topics:
            result = self.execute_rewrite(topic)
            if result and not result.get("error"):
                completed += len(result)
            else:
                failed += 1

        # 保存结果manifest
        manifest_file = self.output_dir / "rewrite_manifest.json"

        # 构建符合canonical workflow的manifest
        canonical_manifest = {
            "run_id": self.run_id,
            "stage": "rewrite",
            "status": "completed" if failed == 0 else "partial_failure",
            "timestamp": datetime.now().isoformat(),
            "output_root": str(self.output_dir),
            "upstream": {
                "draft_manifest": str(self.draft_manifest_file)
            },
            "topics": self.results["topics"],
            "summary": {
                "total_topics": len(topics),
                "completed_versions": completed,
                "failed_topics": failed,
                "versions": self.versions
            }
        }

        manifest_file.write_text(json.dumps(canonical_manifest, ensure_ascii=False, indent=2), encoding='utf-8')

        print(f"\n{'='*70}")
        print(f"Rewrite Stage 5 执行完成")
        print(f"完成版本数: {completed}")
        print(f"失败主题数: {failed}")
        print(f"输出位置: {self.output_dir}")
        print(f"Manifest: {manifest_file}")
        print(f"{'='*70}")

        # 返回JSON结果（供Node.js wrapper使用）
        return {
            "success": failed == 0,
            "run_id": self.run_id,
            "output_dir": str(self.output_dir),
            "manifest_file": str(manifest_file),
            "completed_versions": completed,
            "failed_topics": failed,
            "total_topics": len(topics),
            "versions": self.versions,
            "next_step": "dasheng-stage-publish"
        }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rewrite Stage 5 - 改写执行")
    parser.add_argument("--draft-manifest", required=True, help="Draft manifest JSON文件路径")
    parser.add_argument("--output-dir", help="输出目录（默认：~/Desktop/自媒体创作/00_改写/<run_id>）")
    parser.add_argument("--run-id", help="运行ID（默认：从draft manifest读取）")
    parser.add_argument("--versions", help="版本列表（逗号分隔，默认：wechat_hot,wechat_normal,xiaohongshu_hot,xiaohongshu_normal）")
    parser.add_argument("--json-output", action="store_true", help="输出JSON格式到stdout")

    args = parser.parse_args()

    draft_manifest_file = Path(args.draft_manifest)
    if not draft_manifest_file.exists():
        print(f"错误：Draft manifest文件不存在: {draft_manifest_file}", file=sys.stderr)
        sys.exit(1)

    # 加载draft manifest获取run_id
    draft_manifest = json.loads(draft_manifest_file.read_text(encoding='utf-8'))
    run_id = args.run_id or draft_manifest.get("run_id", datetime.now().strftime("%Y-%m-%d_%H%M%S"))

    # 确定输出目录
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        from path_config import get_output_root; output_dir = get_output_root("rewrite") / run_id

    # 解析版本列表
    if args.versions:
        versions = [v.strip() for v in args.versions.split(",")]
    else:
        versions = DEFAULT_VERSIONS

    executor = RewriteExecutor(draft_manifest_file, output_dir, run_id, versions)
    result = executor.execute_all()

    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
