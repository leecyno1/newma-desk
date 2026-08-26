"""
AI 报告生成路由 - 使用 LLM 生成基金和基金经理分析报告
"""
import subprocess
import logging
import os
from pathlib import Path
from fastapi import APIRouter, HTTPException
from typing import Optional

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/reports", tags=["AI报告"])


@router.post("/manager/{manager_id}")
async def generate_manager_report(manager_id: str):
    """生成基金经理分析报告（使用 fund-manager-report-generator skill）"""
    try:
        report_runner = Path(
            os.environ.get(
                "FUND_MANAGER_REPORT_RUNNER",
                Path.home() / ".claude" / "skills" / "fund-manager-report-generator" / "run.py",
            )
        )
        if not report_runner.is_file():
            raise HTTPException(status_code=503, detail="基金经理报告生成器未配置")
        # 调用 skill 生成报告
        result = subprocess.run(
            [str(report_runner), manager_id],
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode != 0:
            logger.error(f"Skill execution failed: {result.stderr}")
            raise HTTPException(status_code=500, detail=f"报告生成失败: {result.stderr}")

        return {
            "manager_id": manager_id,
            "report": result.stdout,
            "status": "success"
        }
    except HTTPException:
        raise
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="报告生成超时")
    except Exception as e:
        logger.error(f"Generate manager report error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/manager/{manager_id}")
async def get_manager_report(manager_id: str):
    """获取基金经理报告（如果已生成）"""
    # TODO: 实现报告缓存和检索
    return {"manager_id": manager_id, "status": "not_implemented"}
