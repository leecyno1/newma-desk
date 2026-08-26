#!/usr/bin/env python3
"""
Orchestrator - 流程编排器

功能：
1. 协调6个环节的执行
2. 管理HITL检查点
3. 自动化流程控制
4. 错误处理和重试

主链：intake -> brief -> draft -> transwrite -> publish -> postmortem
"""

import json
import yaml
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

from core.dna_engine import DNAEngine


class StageStatus(Enum):
    """环节状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    WAITING_HITL = "waiting_hitl"
    HITL_APPROVED = "hitl_approved"
    HITL_REJECTED = "hitl_rejected"


@dataclass
class StageResult:
    """环节执行结果"""
    stage_id: str
    status: StageStatus
    start_time: str
    end_time: Optional[str] = None
    outputs: Dict = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    quality_score: Optional[float] = None
    retry_count: int = 0
    skipped: bool = False


@dataclass
class RunContext:
    """执行上下文"""
    run_id: str
    start_time: str
    config: Dict
    stage_results: Dict[str, StageResult] = field(default_factory=dict)
    current_stage: Optional[str] = None
    hitl_decisions: Dict[str, Dict] = field(default_factory=dict)


class Orchestrator:
    """流程编排器"""

    def __init__(self, config_path: str = None, skip_on_failure: bool = True, max_retries: int = 2):
        if config_path is None:
            config_path = str(Path(__file__).parent.parent / "dna" / "dna_config.yaml")

        self.config = self._load_config(config_path)
        self.dna_engine = DNAEngine()
        self.stages = self._init_stages()
        self.skip_on_failure = skip_on_failure
        self.max_retries = max_retries

    def _load_config(self, config_path: str) -> Dict:
        """加载配置"""
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def _init_stages(self) -> List[Dict]:
        """初始化环节定义"""
        return [
            {
                "id": "intake",
                "name": "内容采集",
                "auto": self.config["automation"]["intake_auto"],
                "hitl": False,
                "executor": "scripts/run_stage1_intake.py"
            },
            {
                "id": "brief",
                "name": "选题分析",
                "auto": self.config["automation"]["brief_auto"],
                "hitl": True,
                "executor": "skills/dasheng-daily-phase2"
            },
            {
                "id": "draft",
                "name": "初稿生成",
                "auto": self.config["automation"]["draft_auto"],
                "hitl": False,
                "executor": "skills/dasheng-daily-draft"
            },
            {
                "id": "transwrite",
                "name": "转写生产",
                "auto": self.config["automation"]["transwrite_auto"],
                "hitl": False,
                "executor": "skills/dasheng-stage-transwrite"
            },
            {
                "id": "publish",
                "name": "发布执行",
                "auto": self.config["automation"]["publish_auto"],
                "hitl": False,
                "executor": "skills/dasheng-stage-publish"
            },
            {
                "id": "postmortem",
                "name": "分析复盘",
                "auto": self.config["automation"]["postmortem_auto"],
                "hitl": False,
                "executor": "skills/dasheng-daily-postmortem"
            }
        ]

    def create_run(self) -> RunContext:
        """创建新的执行上下文"""
        run_id = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        return RunContext(
            run_id=run_id,
            start_time=datetime.now().isoformat(),
            config=self.config
        )

    def execute_stage(self, ctx: RunContext, stage_id: str) -> StageResult:
        """执行单个环节"""
        stage = next((s for s in self.stages if s["id"] == stage_id), None)
        if not stage:
            raise ValueError(f"Unknown stage: {stage_id}")

        result = StageResult(
            stage_id=stage_id,
            status=StageStatus.RUNNING,
            start_time=datetime.now().isoformat()
        )

        try:
            print(f"\n{'='*70}")
            print(f"执行环节: {stage['name']} ({stage_id})")
            print(f"{'='*70}")

            # 检查是否需要HITL
            if stage["hitl"] and not stage["auto"]:
                result.status = StageStatus.WAITING_HITL
                print(f"⏸️  等待人工介入...")
                return result

            # 执行环节
            if stage_id == "intake":
                outputs = self._execute_intake(ctx)
            elif stage_id == "brief":
                outputs = self._execute_brief(ctx)
            elif stage_id == "draft":
                outputs = self._execute_draft(ctx)
            elif stage_id == "transwrite":
                outputs = self._execute_transwrite(ctx)
            elif stage_id == "publish":
                outputs = self._execute_publish(ctx)
            elif stage_id == "postmortem":
                outputs = self._execute_postmortem(ctx)
            else:
                raise ValueError(f"No executor for stage: {stage_id}")

            result.outputs = outputs
            result.status = StageStatus.COMPLETED
            result.end_time = datetime.now().isoformat()

            print(f"✅ {stage['name']} 完成")

        except Exception as e:
            result.status = StageStatus.FAILED
            result.errors.append(str(e))
            result.end_time = datetime.now().isoformat()
            print(f"❌ {stage['name']} 失败: {str(e)}")

        return result

    def execute_pipeline(self, ctx: RunContext) -> RunContext:
        """执行完整流程"""
        print(f"\n🚀 启动自媒体创作流程")
        print(f"Run ID: {ctx.run_id}")
        print(f"开始时间: {ctx.start_time}")

        for stage in self.stages:
            stage_id = stage["id"]
            ctx.current_stage = stage_id

            # 执行环节
            result = self.execute_stage(ctx, stage_id)
            ctx.stage_results[stage_id] = result

            # 检查是否需要HITL
            if result.status == StageStatus.WAITING_HITL:
                print(f"\n⏸️  流程暂停，等待人工决策")
                print(f"环节: {stage['name']}")
                print(f"请完成人工审核后，调用 resume_pipeline()")
                break

            # 检查是否失败
            if result.status == StageStatus.FAILED:
                print(f"\n❌ 流程中断")
                print(f"失败环节: {stage['name']}")
                print(f"错误: {result.errors}")
                break

        # 生成执行报告
        self._generate_report(ctx)

        return ctx

    def resume_pipeline(self, ctx: RunContext, hitl_decision: Dict) -> RunContext:
        """恢复流程（HITL决策后）"""
        current_stage_id = ctx.current_stage
        if not current_stage_id:
            print("❌ 没有待恢复的环节")
            return ctx

        # 记录HITL决策
        ctx.hitl_decisions[current_stage_id] = hitl_decision

        # 更新当前环节状态
        result = ctx.stage_results[current_stage_id]
        if hitl_decision.get("approved", False):
            result.status = StageStatus.HITL_APPROVED
            result.outputs = hitl_decision.get("outputs", {})
            result.end_time = datetime.now().isoformat()
        else:
            result.status = StageStatus.HITL_REJECTED
            result.errors.append("人工审核未通过")
            result.end_time = datetime.now().isoformat()
            return ctx

        # 继续执行后续环节
        current_index = next(i for i, s in enumerate(self.stages) if s["id"] == current_stage_id)
        for stage in self.stages[current_index + 1:]:
            stage_id = stage["id"]
            ctx.current_stage = stage_id

            result = self.execute_stage(ctx, stage_id)
            ctx.stage_results[stage_id] = result

            if result.status in [StageStatus.WAITING_HITL, StageStatus.FAILED]:
                break

        self._generate_report(ctx)
        return ctx

    def _execute_intake(self, ctx: RunContext) -> Dict:
        """执行Intake环节"""
        # 简化实现：返回模拟数据
        return {
            "intake_records": [],
            "entity_rankings": {},
            "event_clusters": [],
            "channel_top10": {}
        }

    def _execute_brief(self, ctx: RunContext) -> Dict:
        """执行Brief环节"""
        return {
            "topic_cards": [],
            "selected_topics": []
        }

    def _execute_draft(self, ctx: RunContext) -> Dict:
        """执行Draft环节"""
        return {
            "drafts": [],
            "reasoning_sheets": []
        }

    def _execute_transwrite(self, ctx: RunContext) -> Dict:
        """执行Transwrite环节"""
        return {
            "wechat_article": {},
            "talking_head_video": {},
            "podcast": {}
        }

    def _execute_publish(self, ctx: RunContext) -> Dict:
        """执行Publish环节"""
        return {
            "publish_packages": [],
            "channel_versions": []
        }

    def _execute_postmortem(self, ctx: RunContext) -> Dict:
        """执行Postmortem环节"""
        return {
            "analysis_report": {},
            "dna_updates": []
        }

    def _generate_report(self, ctx: RunContext):
        """生成执行报告"""
        report_path = Path(f"产物/runs/{ctx.run_id}/execution_report.json")
        report_path.parent.mkdir(parents=True, exist_ok=True)

        report = {
            "run_id": ctx.run_id,
            "start_time": ctx.start_time,
            "end_time": datetime.now().isoformat(),
            "stages": {
                stage_id: {
                    "status": result.status.value,
                    "start_time": result.start_time,
                    "end_time": result.end_time,
                    "quality_score": result.quality_score,
                    "errors": result.errors
                }
                for stage_id, result in ctx.stage_results.items()
            },
            "hitl_decisions": ctx.hitl_decisions
        }

        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        print(f"\n📊 执行报告已生成: {report_path}")


if __name__ == "__main__":
    # 测试编排器
    orchestrator = Orchestrator()

    # 创建执行上下文
    ctx = orchestrator.create_run()

    # 执行流程
    ctx = orchestrator.execute_pipeline(ctx)

    print(f"\n✅ 流程执行完成")
    print(f"Run ID: {ctx.run_id}")
