"""
基金研究报告生成服务 - 支持 Anthropic 与 OpenAI-compatible API
"""
import os
import json
import logging
import re
import urllib.error
import urllib.request
from typing import Dict, Any, List, Optional

from services.llm_runtime import LlmCircuitOpen, get_llm_runtime_guard

logger = logging.getLogger(__name__)


class LlmGenerationError(RuntimeError):
    """Raised when the configured model cannot return usable content."""


SYSTEM_PROMPT = """你是一位专业的基金研究分析师，擅长深度分析基金经理的投资能力、风格特征和业绩归因。
你的分析报告应当:
1. 数据驱动: 结合具体数据指标进行分析
2. 深入洞察: 不仅描述现象，更挖掘背后原因
3. 客观中立: 既有亮点也有风险提示
4. 结构清晰: 使用分级标题，逻辑递进
5. 严守边界: 只输出基金研究观点和后续跟踪问题，不输出买卖建议、仓位建议、组合配置建议或下游结论
6. 证据克制: 对标记为 unavailable、missing、待补的数据，必须说明证据缺口，不能自行编造持仓、行业或风格结论

报告语言: 中文
报告格式: Markdown"""

REPORT_TYPES = {
    "fund_analysis": "分析一只基金，需要包含以下部分:\n1. 基金概况: 基本信息、规模、成立时间\n2. 业绩分析: 分年度收益、跑赢基准情况、同类排名\n3. 风险分析: 回撤控制、波动率、风险调整收益\n4. 持仓分析: 重仓股特征、行业配置、风格暴露\n5. 归因分析: 收益来源、超额收益分解\n6. 综合评价: 优势、劣势、研究建议",
    "manager_analysis": "分析一位基金经理，需要包含以下部分:\n1. 基金经理概况: 背景、从业年限、管理规模\n2. 投资理念: 投资哲学、选股逻辑、组合管理方式\n3. 风格特征: 基于持仓和净值数据的风格判断\n4. 业绩归因: 历史业绩分析、超额收益来源\n5. 行为一致性: 理念与实际操作的一致性程度\n6. 能力边界: 擅长场景、劣势场景\n7. 综合评价: 核心优势、主要风险点",
    "comparative_analysis": "对比分析多只基金或基金经理，需要包含:\n1. 整体对比: 关键指标对比表格\n2. 收益维度: 各维度收益表现对比\n3. 风险维度: 风险特征对比\n4. 风格对比: 投资风格差异\n5. 综合结论: 各有优劣、适用场景",
    "screening_report": "基于筛选条件生成的基金推荐报告，需要包含:\n1. 筛选概况: 条件说明、筛选结果统计\n2. 推荐列表: 基金名称、评分、一句话推荐理由\n3. 重点推荐: 2-3只基金的深度分析\n4. 风险提示: 筛选结果的局限性",
}


class ClaudeReportGenerator:
    """生成基金/经理研究报告"""

    def __init__(self, api_key: str = None, model: str = "claude-sonnet-4-7-20250514"):
        self.provider = self._resolve_provider()
        self.api_key = api_key or self._resolve_api_key()
        self.model = os.environ.get("LLM_MODEL") or self._resolve_model(model)
        self.base_url = os.environ.get("LLM_BASE_URL") or self._resolve_base_url()
        self._client = None

    def _resolve_provider(self) -> str:
        configured = os.environ.get("LLM_PROVIDER")
        if configured:
            return configured.strip().lower()

        base_url = (
            os.environ.get("LLM_BASE_URL")
            or os.environ.get("SILICONFLOW_BASE_URL")
            or os.environ.get("OPENAI_COMPATIBLE_BASE_URL")
            or os.environ.get("OPENAI_BASE_URL")
            or ""
        ).lower()
        model = (
            os.environ.get("LLM_MODEL")
            or os.environ.get("SILICONFLOW_MODEL")
            or os.environ.get("OPENAI_COMPATIBLE_MODEL")
            or ""
        ).lower()
        if os.environ.get("SILICONFLOW_API_KEY") or "siliconflow" in base_url or "deepseek-ai/" in model:
            return "siliconflow"
        if os.environ.get("OPENAI_COMPATIBLE_API_KEY") or os.environ.get("OPENAI_BASE_URL"):
            return "openai-compatible"
        return "anthropic"

    def _resolve_api_key(self) -> Optional[str]:
        if self.provider in {"siliconflow", "deepseek"}:
            for key_name in ("SILICONFLOW_API_KEY", "LLM_API_KEY"):
                value = (os.environ.get(key_name) or "").strip()
                if len(value) >= 30:
                    return value
            return None
        if self.provider == "openai-compatible":
            for key_name in ("OPENAI_COMPATIBLE_API_KEY", "LLM_API_KEY", "OPENAI_API_KEY"):
                value = (os.environ.get(key_name) or "").strip()
                if len(value) >= 30:
                    return value
            return None
        return os.environ.get("ANTHROPIC_API_KEY")

    def _resolve_model(self, anthropic_default: str) -> str:
        if self.provider in {"siliconflow", "deepseek", "openai-compatible"}:
            return (
                os.environ.get("SILICONFLOW_MODEL")
                or os.environ.get("OPENAI_COMPATIBLE_MODEL")
                or "deepseek-ai/DeepSeek-V4-Flash"
            )
        return anthropic_default

    def _resolve_base_url(self) -> Optional[str]:
        if self.provider in {"siliconflow", "deepseek", "openai-compatible"}:
            return (
                os.environ.get("SILICONFLOW_BASE_URL")
                or os.environ.get("OPENAI_COMPATIBLE_BASE_URL")
                or os.environ.get("OPENAI_BASE_URL")
                or "https://api.siliconflow.cn"
            )
        return None

    @property
    def runtime_key(self) -> str:
        return f"{self.provider}:{self.base_url or 'default'}"

    def health(self) -> Dict[str, Any]:
        return get_llm_runtime_guard().health(
            runtime_key=self.runtime_key,
            configured=bool(self.api_key),
            provider=self.provider,
            model=self.model,
        )

    @property
    def client(self):
        if self.provider in {"siliconflow", "deepseek", "openai-compatible"}:
            return None
        if self._client is None and self.api_key:
            try:
                from anthropic import Anthropic
                self._client = Anthropic(api_key=self.api_key)
            except ImportError:
                logger.warning("Anthropic SDK not available. Install with: pip install anthropic")
        return self._client

    def generate_fund_analysis(
        self,
        fund_data: Dict[str, Any],
        performance_data: Dict[str, Any],
        risk_data: Dict[str, Any],
        holdings_data: List[Dict],
        style_data: Dict[str, Any],
        scoring_result: Dict[str, Any],
        research_reports: List[Dict] = None,
        purchase_plan: str = "sip",
    ) -> str:
        """生成基金分析报告"""
        prompt = self._build_fund_prompt(
            fund_data,
            performance_data,
            risk_data,
            holdings_data,
            style_data,
            scoring_result,
            research_reports,
            purchase_plan,
        )
        return self._call_llm(prompt, "fund_analysis")

    def generate_fund_evaluation_analysis(
        self,
        fund_data: Dict[str, Any],
        evaluation_data: Dict[str, Any],
        factor_evidence: Dict[str, Any],
        attribution_evidence: Dict[str, Any],
        managers: List[Dict[str, Any]],
        research_reports: List[Dict],
        user_question: str = "",
        assessment_summary: Dict[str, Any] = None,
    ) -> str:
        """生成面向基金评价的现场分析，不延伸到交易或个人适当性判断。"""
        prompt = "\n".join([
            "请生成一份面向普通用户的基金评价分析。",
            "严格要求：",
            "1. 只使用下方已提供的证据，缺失数据必须明示说明。",
            "2. 以分类内专业评价为主线，不跨类比较。",
            "3. 因子风险和主动收益归因只用于解释，不参与基金评分。",
            "4. 调研纪要中的观点要标明纪要标题和日期，不得伪造引用。",
            "5. 不输出买入、卖出、仓位、金额或个人适当性建议。",
            "6. evidence_scope=manager_level 的纪要只能作为基金经理层证据，不能写成该基金专属策略或持仓结论。",
            "7. holding_style_peer_evidence 只有 status=peer_percentile_ready 时才能作为量化风格标签；descriptor_ready 只能描述原始描述子。",
            "8. 公开持仓风格同类分位不是完整 Barra 风险模型，必须与正式 Barra 分开表述。",
            "9. 公开持仓稳定性仅比较相邻两期披露的前十大持仓，不得写成真实换手率，且不参与基金评分。",
            "10. period_performance 中 coverage_status=partial 的年度只能描述区间收益，不得引用同类名次。",
            "11. manager_tenure_performance 只有 coverage_status=full_tenure 时才能描述完整任期和同区间排名；partial_since_data_start 只能称为本地可见期，不得把前任历史业绩归因给现任经理。",
            "12. multi_period_evidence 只有 status=long_term_ready 时才能描述完整近 3 年收益风险证据；short_term_only 必须明确长期证据不足。",
            "13. 不得用近 6 月或近 1 年领先推断长期持续；consistency_status=divergent 时必须提示短长期表现分化。",
            "14. holding_style_drift_evidence 只比较同一专业同类组内相邻公开持仓期；不是完整组合、不是 RBSA 或 Barra，且不参与基金评分。",
            "15. manager_tenure_performance.status=not_applicable 时，不得把基金经理任期或经理资料写成评价缺口。",
            "报告结构：一句话结论、基金定位、同类表现、风险与归因、经理与纪要证据、适合继续关注的情形、需要警惕的信号、数据缺口。",
            f"\n## 用户关注的问题\n{user_question or '请做一次完整的基金评价'}",
            "\n## 统一综合评价事实\n```json\n" + self._to_json(assessment_summary or {}) + "\n```",
            "\n## 基金基础数据\n```json\n" + self._to_json(fund_data) + "\n```",
            "\n## 分类内专业评价\n```json\n" + self._to_json(evaluation_data) + "\n```",
            "\n## 多周期收益风险证据\n```json\n" + self._to_json(evaluation_data.get("multi_period_evidence") or {}) + "\n```",
            "\n## Barra 与持仓行业暴露证据\n```json\n" + self._to_json(factor_evidence) + "\n```",
            "\n## Brinson 与补充净值行为解释\n```json\n" + self._to_json(attribution_evidence) + "\n```",
            "\n## 模型边界\n正式 Barra/Brinson 与净值行为解释必须分开表述；不得把 supplementary_nav_factor 标成 Barra，不得把 supplementary_nav_return 标成 Brinson。",
            "\n## 当前基金经理\n```json\n" + self._to_json(managers) + "\n```",
            "\n## 关联调研纪要\n```json\n" + self._to_json(research_reports) + "\n```",
        ])
        timeout_seconds = int(os.environ.get("LLM_EVALUATION_TIMEOUT_SECONDS", "20"))
        return self._call_llm(prompt, "fund_analysis", timeout_seconds=timeout_seconds)

    def generate_manager_analysis(
        self,
        manager_data: Dict[str, Any],
        fund_data: Dict[str, Any],
        performance_data: Dict[str, Any],
        style_data: Dict[str, Any],
        scoring_result: Dict[str, Any],
        research_reports: List[Dict],
        manager_profile: Dict[str, Any] = None,
    ) -> str:
        """生成基金经理分析报告"""
        prompt = self._build_manager_prompt(manager_data, fund_data, performance_data, style_data, scoring_result, research_reports, manager_profile)
        return self._call_llm(prompt, "manager_analysis")

    def generate_comparative_analysis(
        self,
        targets: List[Dict[str, Any]],
        comparison_type: str = "fund",
    ) -> str:
        """生成对比分析报告"""
        prompt = self._build_comparison_prompt(targets, comparison_type)
        return self._call_llm(prompt, "comparative_analysis")

    def extract_research_memo_metadata(self, content: str, filename: str) -> str:
        """Extract only source-grounded memo metadata for later human review."""
        prompt = "\n".join([
            "请从这份基金调研纪要中提取结构化候选，仅返回 JSON，不要 Markdown。",
            "不得推测：每个候选必须给出纪要中逐字存在的短摘录；无法确定就返回空数组。",
            "基金代码统一为 6 位代码加市场后缀（如 000001.OF）；不要输出投资建议。",
            "JSON 格式：",
            '{"manager_names":[{"value":"姓名","confidence":0.0,"excerpt":"原文短句"}],',
            '"fund_ids":[{"value":"000001.OF","confidence":0.0,"excerpt":"原文短句"}],',
            '"classifications":[{"value":"基金或策略分类","confidence":0.0,"excerpt":"原文短句"}],',
            '"style_labels":[{"value":"风格标签","confidence":0.0,"excerpt":"原文短句"}]}',
            f"文件名：{filename}",
            "纪要原文：",
            content[:12_000],
        ])
        return self._call_llm(prompt, "memo_metadata_extraction", strict=True)

    def _to_json(self, data: Any) -> str:
        return json.dumps(data, ensure_ascii=False, indent=2, default=str)

    def _build_fund_prompt(
        self, fund_data, performance, risk, holdings, style, scoring, reports, purchase_plan="sip"
    ) -> str:
        parts = []

        # 基金名称（避免在字符串中使用 ** 语法）
        fund_name = fund_data.get("name", "N/A")
        fund_code = fund_data.get("wind_code", "")
        safe_purchase_plan = "lump_sum" if purchase_plan == "lump_sum" else "sip"
        purchase_plan_label = "一次性买入" if safe_purchase_plan == "lump_sum" else "定投"
        purchase_plan_fields = (
            "申购状态、起购金额、限购、赎回规则、费率、销售风险等级（R1-R5）"
            if safe_purchase_plan == "lump_sum"
            else "申购状态、定投支持、定投起点、限购、赎回规则、费率、销售风险等级（R1-R5）"
        )
        parts.append("请根据以下数据，为基金 [{}] ({}) 生成一份深度分析报告。".format(fund_name, fund_code))
        parts.append(
            "\n## 买前研究口径\n"
            "- 买入方式口径：{}\n"
            "- 进入正式买前判断前必须补齐：{}\n"
            "- 评分、收益风险指标和模型分析只作为研究信号，不能输出正式买前结论；缺失销售证据不得视为中性或默认通过。".format(
                purchase_plan_label,
                purchase_plan_fields,
            )
        )

        parts.append("\n## 基金基本信息\n```json\n" + self._to_json(fund_data) + "\n```")
        parts.append("\n## 业绩数据\n```json\n" + self._to_json(performance) + "\n```")
        parts.append("\n## 风险数据\n```json\n" + self._to_json(risk) + "\n```")
        parts.append("\n## 风格数据 (Barra因子暴露)\n```json\n" + self._to_json(style) + "\n```")
        parts.append("\n## 评分结果\n```json\n" + self._to_json(scoring) + "\n```")

        # 持仓
        if holdings:
            parts.append("\n## 重仓股")
            for h in holdings[:10]:
                sname = h.get("stock_name", "")
                scode = h.get("stock_code", "")
                w = h.get("weight", 0)
                ind = h.get("industry", "N/A")
                parts.append("- {}({}): {:.2%}, 行业:{}".format(sname, scode, w, ind))

        # 调研纪要
        if reports:
            parts.append("\n## 相关调研纪要")
            for r in reports[:3]:
                title = r.get("title", "无标题")
                date = r.get("report_date", "")
                summary = r.get("summary", r.get("content", "")[:500] or "N/A")
                parts.append("\n### {} ({})\n{}\n".format(title, date, summary))

        parts.append("\n请按报告格式要求，生成一份专业、深入、数据驱动的基金分析报告。")
        return "\n".join(parts)

    def _build_manager_prompt(
        self, manager_data, fund_data, performance, style, scoring, reports, profile
    ) -> str:
        parts = []

        # 经理名称
        mgr_name = manager_data.get("name", "N/A")
        parts.append("请根据以下数据，为基金经理 [{}] 生成一份深度分析报告。".format(mgr_name))

        parts.append("\n## 基金经理信息\n```json\n" + self._to_json(manager_data) + "\n```")
        parts.append("\n## 管理的代表基金\n```json\n" + self._to_json(fund_data) + "\n```")
        parts.append("\n## 业绩数据\n```json\n" + self._to_json(performance) + "\n```")
        parts.append("\n## 风格数据\n```json\n" + self._to_json(style) + "\n```")
        parts.append("\n## 评分结果\n```json\n" + self._to_json(scoring) + "\n```")

        if reports:
            parts.append("\n## 调研纪要汇总")
            for r in reports:
                title = r.get("title", "无标题")
                date = r.get("report_date", "")
                summary = r.get("summary", "N/A")
                content = r.get("content", "")
                tags = r.get("tags", [])
                content_snippet = content[:300] + "..." if content else "N/A"
                parts.append("\n### {} ({})\n- 摘要: {}\n- 要点: {}\n- 关键词: {}".format(
                    title, date, summary, content_snippet, ", ".join(tags) if tags else "N/A"))

        if profile:
            parts.append("\n## 经理画像摘要")
            parts.append("- 核心投资理念: {}".format(profile.get("core_philosophy", "N/A")))
            parts.append("- 选股逻辑: {}".format(profile.get("stock_selection_logic", "N/A")))
            parts.append("- 能力优势: {}".format(profile.get("competence_advantages", "N/A")))
            parts.append("- 能力边界: {}".format(profile.get("competence_boundaries", "N/A")))
            parts.append("- 风格标签: {}".format(profile.get("style_label", "N/A")))
            cons = profile.get("philosophy_behavior_consistency", "N/A")
            parts.append("- 理念-行为一致性: {}%".format(cons))

        parts.append("\n请按报告格式要求，生成一份专业、深入、有洞察力的基金经理分析报告。重点关注:")
        parts.append("1. 从调研纪要中提取投资理念和风格特征")
        parts.append("2. 结合数据和纪要对业绩进行归因分析")
        parts.append("3. 评估理念与实际操作的一致性")
        parts.append("4. 给出客观的能力边界和风险提示")
        return "\n".join(parts)

    def _build_comparison_prompt(self, targets: List[Dict], comparison_type: str) -> str:
        parts = ["请对以下{}进行对比分析:\n".format(comparison_type)]
        for i, t in enumerate(targets):
            name = t.get("name", t.get("fund_name", "N/A"))
            parts.append("### {}. {}\n```json\n{}\n```".format(i + 1, name, self._to_json(t)))
        parts.append("\n请生成一份对比分析报告，包含整体对比表格、各维度分析、以及综合结论。")
        return "\n".join(parts)

    def _call_llm(
        self,
        prompt: str,
        report_type: str,
        strict: bool = False,
        timeout_seconds: Optional[int] = None,
    ) -> str:
        """调用模型 API"""
        guard = get_llm_runtime_guard()
        if self.provider in {"siliconflow", "deepseek", "openai-compatible"}:
            if not self.api_key:
                logger.warning("OpenAI-compatible API key not configured. Refusing to generate mock report.")
                message = f"{self.provider} API Key 未配置"
                if strict:
                    raise LlmGenerationError(message)
                return f"## 报告生成失败\n\n{message}；系统已阻止输出模拟研究报告，请配置真实模型服务或使用本地确定性证据报告。"
            try:
                guard.before_request(self.runtime_key)
            except LlmCircuitOpen as error:
                if strict:
                    raise LlmGenerationError(f"模型服务暂时降级，请约 {error.retry_after_seconds} 秒后重试") from error
                return f"## 报告生成失败\n\n模型服务暂时降级，将在约 {error.retry_after_seconds} 秒后恢复尝试；本次使用本地确定性证据报告。"
            return self._call_openai_compatible(
                prompt,
                strict=strict,
                json_object=report_type == "memo_metadata_extraction",
                timeout_seconds=timeout_seconds,
            )

        if not self.client:
            logger.warning("Anthropic client not available. Refusing to generate mock report.")
            if strict:
                raise LlmGenerationError("Anthropic 客户端或 API Key 不可用")
            return "## 报告生成失败\n\nAnthropic 客户端或 API Key 不可用；系统已阻止输出模拟研究报告，请配置真实模型服务或使用本地确定性证据报告。"

        try:
            guard.before_request(self.runtime_key)
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            content = response.content[0].text
            guard.record_success(self.runtime_key)
            return content
        except LlmCircuitOpen as error:
            if strict:
                raise LlmGenerationError(f"模型服务暂时降级，请约 {error.retry_after_seconds} 秒后重试") from error
            return f"## 报告生成失败\n\n模型服务暂时降级，将在约 {error.retry_after_seconds} 秒后恢复尝试；本次使用本地确定性证据报告。"
        except Exception as e:
            guard.record_failure(self.runtime_key, e)
            logger.error("Anthropic API error: {}".format(e))
            if strict:
                raise LlmGenerationError(self._model_error_message(e)) from e
            return "## 报告生成失败\n\n错误: {}\n\n请检查API配置后重试。".format(e)

    def _call_openai_compatible(
        self,
        prompt: str,
        strict: bool = False,
        json_object: bool = False,
        timeout_seconds: Optional[int] = None,
    ) -> str:
        guard = get_llm_runtime_guard()
        base_url = self.base_url.rstrip("/")
        url = base_url + ("/chat/completions" if base_url.endswith("/v1") else "/v1/chat/completions")
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 8192,
        }
        if json_object:
            payload["response_format"] = {"type": "json_object"}
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        timeout = timeout_seconds or int(os.environ.get("LLM_TIMEOUT_SECONDS", "240"))
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
            # 剥离思考型模型（如 MiniMax-M3）的 <think>…</think> 推理段，只保留正式报告
            if isinstance(content, str) and "</think>" in content:
                content = re.sub(r"^\s*<think>[\s\S]*?</think>\s*", "", content)
                if not content.strip() and isinstance(data["choices"][0]["message"].get("reasoning_content"), str):
                    # 极端情况：正文全在思考段时拒绝输出（避免空报告）
                    raise ValueError("模型仅返回思考段，无正式内容")
            guard.record_success(self.runtime_key)
            return content
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="ignore")
            guard.record_failure(self.runtime_key, f"HTTP {error.code}: {detail[:160]}")
            logger.error("OpenAI-compatible API HTTP error %s: %s", error.code, detail[:500])
            if strict:
                raise LlmGenerationError(self._model_error_message(error, status_code=error.code)) from error
            return "## 报告生成失败\n\n模型服务返回错误，请检查 API Key、模型名和供应商配额。"
        except Exception as error:
            guard.record_failure(self.runtime_key, error)
            logger.error("OpenAI-compatible API error: %s", error)
            if strict:
                raise LlmGenerationError(self._model_error_message(error)) from error
            return "## 报告生成失败\n\n错误: {}\n\n请检查模型服务配置后重试。".format(error)

    def _model_error_message(self, error: Exception, status_code: Optional[int] = None) -> str:
        if status_code in {401, 403}:
            return f"{self.provider} 鉴权失败，请更新该供应商的 API Key"
        if status_code == 429:
            return f"{self.provider} 请求受限或额度不足"
        message = str(error or "模型请求失败").strip().replace("\n", " ")
        return f"{self.provider} 模型请求失败：{message[:180]}"

# 全局单例
_report_generator: Optional[ClaudeReportGenerator] = None


def get_report_generator() -> ClaudeReportGenerator:
    global _report_generator
    if _report_generator is None:
        _report_generator = ClaudeReportGenerator()
    return _report_generator
