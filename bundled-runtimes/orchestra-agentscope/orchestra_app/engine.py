from __future__ import annotations

import asyncio
import hashlib
import json
import re
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from agentscope.agent import Agent
from agentscope.credential import OpenAICredential
from agentscope.event import (
    TextBlockDeltaEvent,
    ThinkingBlockDeltaEvent,
    ToolCallDeltaEvent,
    ToolCallEndEvent,
    ToolCallStartEvent,
    ToolResultEndEvent,
    ToolResultStartEvent,
    ToolResultTextDeltaEvent,
)
from agentscope.message import Msg, TextBlock, ToolCallBlock, ToolResultState, UserMsg
from agentscope.model import OpenAIChatModel
from agentscope.tool import Toolkit, ToolResponse

from .credentials import CredentialBundle, credential_scope
from .financial_tools import financial_function_tools
from .models import AgentProfile
from .prompts import (
    build_data_foundation_system_prompt,
    build_orchestra_system_prompt,
    build_system_prompt,
)
from .registry import (
    registered_skill_names,
    required_skill_names,
    skill_catalog,
    skill_paths_for,
)
from .settings import settings


EventCallback = Callable[[str, dict[str, Any]], Awaitable[None]]


class DemoEngine:
    async def run_agent(
        self,
        profile: AgentProfile,
        prompt: str,
        phase: str,
        emit: EventCallback,
    ) -> str:
        del prompt
        for stage, summary in self._thinking_summaries(profile, phase):
            await emit("agent.thinking", {"stage": stage, "summary": summary})
            await asyncio.sleep(settings.demo_delay)
        output = self._build_output(profile, phase)
        for chunk in self._chunks(output, 42):
            await emit("agent.output.delta", {"delta": chunk})
            await asyncio.sleep(settings.demo_delay / 3)
        return output

    @staticmethod
    def _thinking_summaries(profile: AgentProfile, phase: str) -> list[tuple[str, str]]:
        primary_skill = profile.skills[0] if profile.skills else "专属研究框架"
        if phase == "intervention":
            return [
                ("framing", "读取人类干预指令、已有报告与证据缺口"),
                ("framework", f"使用 {primary_skill} 对原结论执行定向复核"),
                ("synthesis", "形成增量结论、新增证据与未解问题"),
            ]
        if phase == "research":
            return [
                ("framing", "拆解议题，定义核心变量、时间窗口与验证边界"),
                ("framework", f"载入 {primary_skill}，建立证据与反证清单"),
                ("synthesis", f"从{profile.focus}维度收敛阶段判断与配置影响"),
            ]
        return [
            ("framing", "读取群体研究成果，定位共识、冲突与数据缺口"),
            ("framework", f"按{profile.style}审视组合建议与风险预算"),
            ("synthesis", "形成投票意见、止错条件与可执行仓位约束"),
        ]

    @staticmethod
    def _chunks(text: str, size: int) -> list[str]:
        return [text[index : index + size] for index in range(0, len(text), size)]

    @staticmethod
    def _build_output(profile: AgentProfile, phase: str) -> str:
        if phase == "intervention":
            return (
                f"# {profile.id} {profile.name}｜单席干预增量报告\n\n"
                f"【增量判断】按{profile.focus}视角完成定向复核；当前为推演模式，"
                "不将未调用真实数据接口的内容伪装成新证据。\n\n"
                "【结论变化】原结论保留，但置信度维持低位。\n\n"
                "【新增证据】无；推演模式不请求 Tushare、Tavily 或 IMA。\n\n"
                "【未解问题】需在 live 模式下完成数据核验后再更新投资判断。"
            )
        if phase == "research":
            return (
                f"【核心观点】{profile.name}将从{profile.focus}维度检验议题，当前为流程推演，"
                "尚未调用真实金融数据。\n"
                "【置信度】低\n"
                f"【关键假设】研究方法遵循{profile.style}\n"
                "【数据与来源】当前推演未请求 Tushare、Tavily 或 IMA。\n"
                "【反证条件】真实数据与当前方向相反；关键假设无法通过交叉验证。\n"
                "【对配置的影响】进入真实模式并取得数据后再形成仓位建议。"
            )
        return (
            f"【同意】认可研究组需要以可核验数据支持结论。\n"
            f"【质疑】{profile.name}认为当前推演材料不足以支持真实交易。\n"
            "【组合建议】暂不形成真实仓位，仅验证多席位协作链路。\n"
            "【风险预算】真实数据未接入前风险预算为0。\n"
            "【投票】有条件赞成"
        )


class AgentScopeEngine:
    INVESTOR_LENS_WORKFLOWS = {
        "PM-01": "workflows/cathie-wood.md",
        "PM-02": "workflows/warren-buffett-scorecard.md",
        "PM-03": "workflows/charlie-munger.md",
        "PM-04": "workflows/duan-yongping-seller.md",
        "PM-05": "workflows/peter-lynch.md",
        "PM-06": "workflows/howard-marks-cycle.md",
    }

    def __init__(self, credentials: CredentialBundle | None = None) -> None:
        self.credentials = credentials or CredentialBundle.from_settings()
        if not self.credentials.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY 未配置，不能运行 live 模式。")
        self.credential = OpenAICredential(
            api_key=self.credentials.openai_api_key,
            base_url=self.credentials.openai_base_url,
        )

    def _create_agent(
        self,
        profile: AgentProfile,
        system_prompt: str | None = None,
        *,
        max_tokens: int = 5200,
        parallel_tool_calls: bool = True,
    ) -> Agent:
        credential = self.credential
        model_name = self.credentials.openai_model or settings.openai_model
        if profile.connection.kind == "openai_compatible":
            api_key = (
                self.credentials.agent_secrets.get(profile.connection.secret_id or "")
                or self.credentials.openai_api_key
            )
            if not api_key:
                raise RuntimeError(f"{profile.id} 的独立大模型未配置 API Key。")
            credential = OpenAICredential(
                api_key=api_key,
                base_url=profile.connection.endpoint or self.credentials.openai_base_url,
            )
            model_name = profile.connection.model or model_name
        model = OpenAIChatModel(
            credential=credential,
            model=model_name,
            parameters=OpenAIChatModel.Parameters(
                thinking_enable=True,
                reasoning_effort="medium",
                temperature=0.3,
                max_tokens=max_tokens,
                parallel_tool_calls=parallel_tool_calls,
            ),
            stream=True,
        )
        toolkit = Toolkit(
            tools=financial_function_tools(),
            skills_or_loaders=skill_paths_for(profile),
        )
        return Agent(
            name=f"{profile.id} {profile.name}",
            system_prompt=system_prompt or build_system_prompt(profile),
            model=model,
            toolkit=toolkit,
        )

    async def run_agent(
        self,
        profile: AgentProfile,
        prompt: str,
        phase: str,
        emit: EventCallback,
    ) -> str:
        if profile.connection.kind == "external_http":
            return await self._run_external_agent(profile, prompt, phase, emit)
        await emit(
            "agent.thinking",
            {
                "stage": "framing",
                "summary": "读取角色框架与已注入 Skills，拆解任务和验证边界",
            },
        )
        agent = self._create_agent(profile)
        skill_context = await self._activate_required_skills(agent, profile, emit)
        enriched_prompt = (
            f"{prompt}\n\n"
            "<required-skill-context>\n"
            "以下内容已由系统通过 AgentScope Skill 查看器读取。研究时必须遵循，"
            "不得只引用名称而忽略流程。\n\n"
            f"{skill_context}\n"
            "</required-skill-context>"
        )
        return await self._stream_reply(agent, enriched_prompt, emit)

    async def _run_external_agent(
        self,
        profile: AgentProfile,
        prompt: str,
        phase: str,
        emit: EventCallback,
    ) -> str:
        endpoint = profile.connection.endpoint
        if not endpoint:
            raise RuntimeError(f"{profile.id} 未配置外部 Agent Endpoint。")
        await emit(
            "agent.thinking",
            {"stage": "dispatch", "summary": "将角色边界、Skills 与任务发送给外部 Agent"},
        )
        skill_context = await self._external_skill_context(profile, emit)
        secret = self.credentials.agent_secrets.get(profile.connection.secret_id or "")
        headers = {"Accept": "text/event-stream, application/x-ndjson, application/json"}
        if secret:
            headers["Authorization"] = f"Bearer {secret}"
        payload = {
            "agent": {
                "id": profile.id,
                "name": profile.name,
                "title": profile.title,
                "group": profile.group,
                "focus": profile.focus,
                "persona": profile.persona,
                "style": profile.style,
                "default_prompt": profile.default_prompt,
            },
            "phase": phase,
            "prompt": prompt,
            "skills": required_skill_names(profile),
            "skill_context": skill_context,
        }
        await emit("agent.tool.started", {"tool": "external_agent"})
        await emit(
            "agent.tool.input",
            {"tool": "external_agent", "params": {"endpoint": endpoint, "phase": phase}},
        )
        output = ""
        timeout = httpx.Timeout(float(profile.connection.timeout_seconds))
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            async with client.stream("POST", endpoint, json=payload, headers=headers) as response:
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").lower()
                if "text/event-stream" in content_type or "application/x-ndjson" in content_type:
                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line or line.startswith(":"):
                            continue
                        if line.startswith("data:"):
                            line = line[5:].strip()
                        if line == "[DONE]":
                            break
                        delta = self._external_delta(line)
                        if delta:
                            output += delta
                            await emit("agent.output.delta", {"delta": delta})
                else:
                    body = await response.aread()
                    output = self._external_output(body, content_type)
                    for index in range(0, len(output), 120):
                        await emit("agent.output.delta", {"delta": output[index : index + 120]})
        if not output.strip():
            raise RuntimeError(f"{profile.id} 的外部 Agent 未返回可用内容。")
        await emit(
            "agent.tool.completed",
            {"tool": "external_agent", "status": "success", "source": endpoint, "excerpt": output[:600]},
        )
        return output.strip()

    async def _external_skill_context(
        self,
        profile: AgentProfile,
        emit: EventCallback,
    ) -> str:
        sections: list[str] = []
        remaining = settings.max_total_skill_context_chars
        for skill in required_skill_names(profile):
            path = skill_catalog().get(skill)
            skill_file = path / "SKILL.md" if path else None
            if not skill_file or not skill_file.is_file():
                raise RuntimeError(f"必选 Skill 无法读取：{skill}")
            await emit("agent.skill.registered", {"skill": skill})
            budget = min(settings.max_skill_context_chars, remaining)
            markdown = skill_file.read_text(encoding="utf-8")[:budget]
            remaining = max(0, remaining - len(markdown))
            await emit(
                "agent.skill.used",
                {"skill": skill, "source": "external-agent-preload", "context_chars": len(markdown)},
            )
            sections.append(f"## Skill: {skill}\n\n{markdown}")
        return "\n\n".join(sections)

    @staticmethod
    def _external_delta(line: str) -> str:
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            return line
        if isinstance(value, str):
            return value
        if not isinstance(value, dict):
            return ""
        return str(value.get("delta") or value.get("content") or value.get("output") or "")

    @staticmethod
    def _external_output(body: bytes, content_type: str) -> str:
        text = body.decode("utf-8", errors="replace")
        if "json" not in content_type:
            return text
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            return text
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            message = value.get("message")
            if isinstance(message, dict):
                message = message.get("content")
            return str(value.get("output") or value.get("content") or message or "")
        return ""

    async def run_data_foundation(
        self,
        prompt: str,
        emit: EventCallback,
    ) -> str:
        profile = AgentProfile(
            id="DATA-FOUNDATION",
            name="共享数据基座",
            title="Orchestra 三端证据采集层",
            group="编排层",
            focus="结构化数据、公开网络与 IMA 知识库",
            persona="中立、可审计的数据取证与交叉验证节点",
            style="只记录事实、来源、口径冲突和数据缺口，不给投资结论",
            role_card="",
            skills=[],
            risk_controls=[
                "不得编造未取得的数据",
                "不得把搜索摘要当作原始事实",
                "不得输出投资结论",
            ],
        )
        await emit(
            "agent.thinking",
            {"stage": "framing", "summary": "识别议题实体、市场范围与三端取证路径"},
        )
        agent = self._create_agent(
            profile,
            build_data_foundation_system_prompt(),
            max_tokens=3200,
            parallel_tool_calls=False,
        )
        return await self._stream_reply(agent, prompt, emit)

    async def _activate_required_skills(
        self,
        agent: Agent,
        profile: AgentProfile,
        emit: EventCallback,
    ) -> str:
        await agent.toolkit.get_skill_instructions()
        for skill in registered_skill_names(profile):
            await emit("agent.skill.registered", {"skill": skill})

        activated: list[str] = []
        required = required_skill_names(profile)
        remaining_budget = settings.max_total_skill_context_chars
        for index, skill in enumerate(required):
            response: ToolResponse | None = None
            tool_call = ToolCallBlock(
                id=f"required-skill-{profile.id}-{index}",
                name="Skill",
                input=json.dumps({"skill": skill}, ensure_ascii=False),
            )
            async for result in agent.toolkit.call_tool(tool_call, agent.state):
                if isinstance(result, ToolResponse):
                    response = result

            markdown = ""
            if response is not None and response.state == ToolResultState.SUCCESS:
                markdown = "\n".join(
                    block.text for block in response.content if isinstance(block, TextBlock)
                ).strip()
            if not markdown:
                raise RuntimeError(f"必选 Skill 无法读取：{skill}")

            workflow_name = self.INVESTOR_LENS_WORKFLOWS.get(profile.id)
            workflow = ""
            if skill == "llmquant-investor-lenses" and workflow_name:
                skill_root = skill_catalog().get(skill)
                workflow_path = skill_root / workflow_name if skill_root else None
                if workflow_path and workflow_path.exists():
                    workflow = workflow_path.read_text(encoding="utf-8").strip()

            skills_left = len(required) - index
            fair_share = max(2000, remaining_budget // max(1, skills_left))
            skill_budget = min(settings.max_skill_context_chars, fair_share)
            if workflow:
                workflow_budget = min(len(workflow), max(1800, skill_budget // 2))
                base_budget = max(1200, skill_budget - workflow_budget - 80)
                compact_markdown = markdown[:base_budget]
                if len(markdown) > base_budget:
                    compact_markdown += "\n\n[Skill 正文已按上下文预算截断]"
                compact_workflow = workflow[:workflow_budget]
                if len(workflow) > workflow_budget:
                    compact_workflow += "\n\n[专属工作流已按上下文预算截断]"
                markdown = (
                    f"{compact_markdown}\n\n"
                    f"## Activated workflow for {profile.id}\n\n{compact_workflow}"
                )
            elif len(markdown) > skill_budget:
                markdown = (
                    f"{markdown[:skill_budget]}\n\n"
                    "[Skill 正文已按上下文预算截断；保留了定义、工作流入口与核心规则]"
                )
            remaining_budget = max(0, remaining_budget - len(markdown))

            await emit(
                "agent.skill.used",
                {
                    "skill": skill,
                    "source": "orchestrator-preload",
                    "workflow": workflow_name if skill == "llmquant-investor-lenses" else None,
                    "context_chars": len(markdown),
                },
            )
            activated.append(f"## Skill: {skill}\n\n{markdown}")
        return "\n\n".join(activated)

    async def run_orchestra(
        self,
        prompt: str,
        emit: EventCallback,
    ) -> str:
        profile = AgentProfile(
            id="ORCHESTRA",
            name="Orchestra 主席",
            title="投资决策委员会主席",
            group="编排层",
            focus="证据审计、分歧收敛、风险预算与正式决议",
            persona="中立、审慎、可审计的投委会流程负责人",
            style="先核验证据，再保留分歧，最后形成带复议条件的决议",
            role_card="",
            skills=["council", "data-quality-checker", "exposure-coach"],
            available_skills=["council", "data-quality-checker", "exposure-coach"],
            risk_controls=[
                "不得替任何固定席位投票",
                "不得添加席位材料之外的具体金融数据",
                "关键数据缺失时必须降低置信度或触发复议",
            ],
        )
        await emit(
            "agent.thinking",
            {
                "stage": "convergence",
                "summary": "审计全体席位证据、分歧、少数意见与风险约束",
            },
        )
        agent = self._create_agent(profile, build_orchestra_system_prompt())
        return await self._stream_reply(agent, prompt, emit)

    async def _stream_reply(
        self,
        agent: Agent,
        prompt: str,
        emit: EventCallback,
    ) -> str:
        final_message: Msg | None = None
        output = ""
        draft_buffer = ""
        reasoning_announced = False
        synthesis_announced = False
        tool_calls: dict[str, dict[str, str]] = {}
        seen_sections: set[str] = set()
        with credential_scope(self.credentials):
            async for item in agent.reply_stream(
                UserMsg("Orchestra", prompt),
                yield_final_msg=True,
            ):
                if isinstance(item, TextBlockDeltaEvent):
                    if not synthesis_announced:
                        synthesis_announced = True
                        await emit(
                            "agent.thinking",
                            {
                                "stage": "synthesis",
                                "summary": "整理证据、反证条件与可执行结论",
                            },
                        )
                    output += item.delta
                    draft_buffer += item.delta
                    for section in re.findall(r"【([^】\n]{1,40})】", output[-500:]):
                        if section not in seen_sections:
                            seen_sections.add(section)
                            await emit("agent.report.section", {"section": section})
                    if len(draft_buffer) >= 90 or draft_buffer.endswith(("\n", "。", "；")):
                        await emit("agent.output.delta", {"delta": draft_buffer})
                        draft_buffer = ""
                elif isinstance(item, ThinkingBlockDeltaEvent):
                    if not reasoning_announced:
                        reasoning_announced = True
                        await emit(
                            "agent.thinking",
                            {
                                "stage": "reasoning",
                                "summary": "交叉核对关键假设，检查数据缺口与反证路径",
                            },
                        )
                elif isinstance(item, ToolCallStartEvent):
                    tool_calls[item.tool_call_id] = {
                        "name": item.tool_call_name,
                        "input": "",
                        "result": "",
                    }
                    await emit(
                        "agent.thinking",
                        {
                            "stage": "evidence",
                            "summary": f"调用 {item.tool_call_name} 核验关键数据与来源",
                        },
                    )
                    await emit("agent.tool.started", {"tool": item.tool_call_name})
                elif isinstance(item, ToolCallDeltaEvent):
                    call = tool_calls.setdefault(
                        item.tool_call_id,
                        {"name": "", "input": "", "result": ""},
                    )
                    call["input"] += item.delta
                elif isinstance(item, ToolCallEndEvent):
                    call = tool_calls.get(item.tool_call_id)
                    if call and call["name"] == "Skill":
                        skill = self._skill_name_from_input(call["input"])
                        if skill:
                            await emit("agent.skill.used", {"skill": skill, "source": "model"})
                    elif call:
                        await emit(
                            "agent.tool.input",
                            {
                                "tool": call["name"],
                                "params": self._safe_tool_params(call["input"]),
                            },
                        )
                elif isinstance(item, ToolResultStartEvent):
                    tool_calls.setdefault(
                        item.tool_call_id,
                        {"name": item.tool_call_name, "input": "", "result": ""},
                    )
                elif isinstance(item, ToolResultTextDeltaEvent):
                    call = tool_calls.setdefault(
                        item.tool_call_id,
                        {"name": "", "input": "", "result": ""},
                    )
                    call["result"] += item.delta
                elif isinstance(item, ToolResultEndEvent):
                    call = tool_calls.pop(item.tool_call_id, None)
                    if call and call["name"] != "Skill":
                        evidence_payload = self._evidence_payload(call, str(item.state))
                        await emit(
                            "agent.tool.completed",
                            {
                                "tool": call["name"],
                                "status": str(item.state),
                                "source": evidence_payload["source_name"],
                                "excerpt": evidence_payload["excerpt"][:600],
                            },
                        )
                        await emit(
                            "agent.evidence.recorded",
                            evidence_payload,
                        )
                elif isinstance(item, Msg):
                    final_message = item
        if draft_buffer:
            await emit("agent.output.delta", {"delta": draft_buffer})
        if final_message is not None:
            final_text = final_message.get_text_content() or ""
            if final_text and not output:
                output = final_text
                await emit("agent.output.delta", {"delta": final_text})
        return output.strip()

    @staticmethod
    def _safe_tool_params(raw: str) -> dict[str, Any]:
        try:
            value = json.loads(raw or "{}")
        except json.JSONDecodeError:
            return {"raw": raw[:500]}

        def redact(item: Any) -> Any:
            if isinstance(item, dict):
                return {
                    str(key): "[REDACTED]"
                    if any(token in str(key).lower() for token in ("token", "api_key", "apikey", "secret", "password"))
                    else redact(child)
                    for key, child in item.items()
                }
            if isinstance(item, list):
                return [redact(child) for child in item[:20]]
            if isinstance(item, str):
                return item[:500]
            return item

        redacted = redact(value)
        return redacted if isinstance(redacted, dict) else {"value": redacted}

    @staticmethod
    def _skill_name_from_input(raw: str) -> str | None:
        try:
            payload = json.loads(raw)
            skill = payload.get("skill")
            return str(skill) if skill else None
        except (json.JSONDecodeError, AttributeError):
            match = re.search(r'["\']skill["\']\s*:\s*["\']([^"\']+)', raw)
            return match.group(1) if match else None

    @staticmethod
    def _evidence_payload(call: dict[str, str], status: str) -> dict[str, Any]:
        try:
            params = json.loads(call.get("input", "") or "{}")
        except json.JSONDecodeError:
            params = {"raw": call.get("input", "")[:1000]}
        raw_result = call.get("result", "")
        try:
            result = json.loads(raw_result)
        except json.JSONDecodeError:
            result = {}
        source_name = str(result.get("source") or call.get("name") or "unknown")
        source_url = None
        observed_at = None
        interface_name = None
        if call.get("name") == "tushare_query":
            interface_name = str(result.get("api_name") or params.get("api_name") or "") or None
            query_params = result.get("params") or params.get("params") or {}
            observed_at = str(
                query_params.get("trade_date")
                or query_params.get("end_date")
                or query_params.get("start_date")
                or "",
            ) or None
        elif call.get("name") == "tavily_search":
            interface_name = str(result.get("query") or params.get("query") or "") or None
            results = result.get("results") or []
            if results:
                source_url = str(results[0].get("url") or "") or None
                observed_at = str(results[0].get("published_date") or "") or None
        elif call.get("name") in {"a_stock_data", "global_stock_data"}:
            interface_name = str(result.get("action") or params.get("action") or "") or None
            rows = result.get("rows") or []
            if rows:
                observed_at = str(
                    rows[-1].get("date")
                    or rows[-1].get("timestamp")
                    or rows[0].get("publish_date")
                    or "",
                ) or None
        elif call.get("name") == "ima_knowledge_search":
            interface_name = str(result.get("query") or params.get("query") or "") or None
        excerpt = raw_result[:4000]
        return {
            "id": uuid.uuid4().hex,
            "source_name": source_name,
            "source_url": source_url,
            "observed_at": observed_at,
            "tool_name": call.get("name") or "unknown",
            "interface_name": interface_name,
            "params": params,
            "status": status,
            "excerpt": excerpt,
            "content_hash": hashlib.sha256(raw_result.encode("utf-8")).hexdigest(),
        }
