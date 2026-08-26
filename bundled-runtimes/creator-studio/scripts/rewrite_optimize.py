#!/usr/bin/env python3
"""
Rewrite Stage 5 优化重新生成脚本

只重新生成质量不达标的版本：
- 质量评分 < 7.0
- 字数偏差 > 30%
- 锚点保留率 < 80%
"""

import json
import sys
from pathlib import Path
from datetime import datetime
import anthropic

# 添加skills路径
skills_path = Path(__file__).parent.parent / "skills" / "dasheng-media-rewrite-v2"
sys.path.insert(0, str(skills_path))

from core.enhanced_prompt_builder import EnhancedPromptBuilder
from core.quality_scorer import QualityScorer
from core.anchor_mapper import AnchorMapper
from core.version_generator import VersionGenerator

# 配置
from path_config import get_output_root
RUN_ID = "2026-04-11_085602"
DRAFT_DIR = get_output_root("draft") / RUN_ID
OUTPUT_DIR = get_output_root("rewrite") / RUN_ID
MANIFEST_FILE = OUTPUT_DIR / "rewrite_manifest.json"

class RewriteOptimizer:
    def __init__(self):
        self.client = anthropic.Anthropic()
        self.generator = VersionGenerator()

        # 加载现有manifest
        if MANIFEST_FILE.exists():
            with open(MANIFEST_FILE, 'r', encoding='utf-8') as f:
                self.manifest = json.load(f)
        else:
            raise FileNotFoundError(f"Manifest not found: {MANIFEST_FILE}")

    def should_regenerate(self, version_result: dict) -> tuple[bool, str]:
        """判断是否需要重新生成，返回(是否重做, 原因)"""
        if version_result.get("status") != "completed":
            return True, "生成失败"

        reasons = []

        # 质量评分低于7.0
        score = version_result.get("quality_score", 0)
        if score < 7.0:
            reasons.append(f"评分过低({score}/10)")

        # 字数偏差超过30%
        word_count = version_result.get("word_count", 0)
        target = version_result.get("target_word_count", 1000)
        deviation = abs(word_count - target) / target
        if deviation > 0.3:
            reasons.append(f"字数偏差{int(deviation*100)}%")

        # 锚点保留率低于80%
        anchor_rate = version_result.get("anchor_preserved_rate", 0)
        if anchor_rate < 80:
            reasons.append(f"锚点保留率{anchor_rate}%")

        if reasons:
            return True, " + ".join(reasons)
        return False, ""

    def load_draft(self, topic: str) -> str:
        """加载初稿文件"""
        draft_file = DRAFT_DIR / f"03_标准初稿_{topic}.md"
        if not draft_file.exists():
            raise FileNotFoundError(f"Draft file not found: {draft_file}")
        return draft_file.read_text(encoding='utf-8')

    def generate_rewrite(self, topic: str, version_id: str, original_text: str) -> dict:
        """生成单个改写版本"""
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

        # 调用Claude API
        message = self.client.messages.create(
            model="claude-opus-4-6",
            max_tokens=4096,
            system="你是一位专业的内容改写专家。请严格按照用户提供的改写规则执行，直接输出改写后的完整文稿，不要包含任何解释或元评论。",
            messages=[{"role": "user", "content": prompt}]
        )
        rewritten_text = message.content[0].text

        # 运行质量评分
        scorer = QualityScorer(
            platform=platform,
            tone=tone,
            original_doc=original_text,
            final_snapshot={"sections": []}
        )
        quality_report = scorer.score(rewritten_text)

        # 运行锚点映射
        anchor_mapper = AnchorMapper(original_text, rewritten_text)
        anchor_report = anchor_mapper.generate_report()

        return {
            "status": "completed",
            "content": rewritten_text,
            "quality_score": quality_report.overall_score,
            "quality_status": quality_report.status,
            "anchor_preserved_rate": anchor_report.preserved_rate,
            "word_count": len(rewritten_text),
            "target_word_count": schema["word_count"]["target"]
        }

    def optimize_all(self):
        """优化所有需要重做的版本"""
        print("\n🔄 启动Rewrite优化重新生成")
        print(f"Run ID: {RUN_ID}")
        print(f"Manifest: {MANIFEST_FILE}")

        regenerate_count = 0
        skip_count = 0
        improved_count = 0

        for topic, versions in self.manifest["topics"].items():
            print(f"\n{'='*70}")
            print(f"检查主题: {topic}")
            print(f"{'='*70}")

            # 加载初稿
            try:
                original_draft = self.load_draft(topic)
            except FileNotFoundError as e:
                print(f"  ✗ 跳过: {e}")
                continue

            for version_id, version_result in versions.items():
                should_redo, reason = self.should_regenerate(version_result)

                if not should_redo:
                    print(f"  ✓ {version_id}: 质量达标，跳过")
                    skip_count += 1
                    continue

                print(f"  → {version_id}: 需要重做（{reason}）")
                old_score = version_result.get("quality_score", 0)

                try:
                    # 重新生成
                    new_result = self.generate_rewrite(topic, version_id, original_draft)
                    new_score = new_result["quality_score"]

                    # 更新manifest
                    self.manifest["topics"][topic][version_id] = new_result

                    # 保存改写文件
                    output_file = OUTPUT_DIR / f"06_改写_{topic[:10]}_{version_id}.md"
                    with open(output_file, 'w', encoding='utf-8') as f:
                        f.write(new_result["content"])

                    regenerate_count += 1
                    if new_score > old_score:
                        improved_count += 1
                        print(f"    ✓ 完成: {old_score:.1f} → {new_score:.1f} (+{new_score-old_score:.1f})")
                    else:
                        print(f"    ⚠️ 完成: {old_score:.1f} → {new_score:.1f} (未改善)")

                    print(f"    字数: {new_result['word_count']} (目标: {new_result['target_word_count']})")
                    print(f"    锚点: {new_result['anchor_preserved_rate']}%")

                except Exception as e:
                    print(f"    ✗ 失败: {str(e)}")

        # 保存更新后的manifest
        self.manifest["timestamp"] = datetime.now().isoformat()
        with open(MANIFEST_FILE, 'w', encoding='utf-8') as f:
            json.dumps(self.manifest, f, ensure_ascii=False, indent=2)

        print(f"\n{'='*70}")
        print(f"优化完成")
        print(f"重新生成: {regenerate_count}个")
        print(f"跳过: {skip_count}个")
        print(f"质量改善: {improved_count}个")
        print(f"{'='*70}")

if __name__ == "__main__":
    optimizer = RewriteOptimizer()
    optimizer.optimize_all()
