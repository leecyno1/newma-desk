from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
INDEX_HTML = PROJECT_ROOT / "static" / "index.html"


def test_primary_module_labels_use_new_names():
    source = INDEX_HTML.read_text(encoding="utf-8")

    assert 'data-module="send-management">消息群发<' in source
    assert 'data-module="contact-management">分析师评分<' in source
    assert '高评分分析师' in source
    assert '消息群发默认启用“敬”' in source


def test_contact_table_exposes_loading_failure_and_retry_states():
    source = INDEX_HTML.read_text(encoding="utf-8")
    start = source.index("async function loadContactsFromBackend()")
    end = source.index("async function updateContactScore", start)
    section = source[start:end]

    assert "联系人加载中" in section
    assert "if (!r.ok)" in section
    assert "Array.isArray(items)" in section
    assert "联系人加载失败" in section
    assert "loadContactsFromBackend()\">重试" in section



def test_watch_engine_tables_use_signal_columns_and_summary_fallbacks():
    source = INDEX_HTML.read_text(encoding='utf-8')
    assert '<th class="read">来源</th>' in source
    assert '<th class="share">热度</th>' in source
    assert '<th class="recommend">新鲜度</th>' in source
    assert '<th class="transcribe">信号</th>' in source
    assert '<th class="content-type">议题</th>' in source
    assert '<th class="tone">信号</th>' in source
    assert 'function _deriveBriefFromItem' in source
    assert 'function _formatFreshness' in source
    assert '暂无摘要，可打开原文查看。' in source
    assert '暂无要点，可点击原文查看。' in source


def test_ai_summary_loads_config_before_local_generation():
    source = INDEX_HTML.read_text(encoding='utf-8')
    block = source.split('if (!contactRatings || Object.keys(contactRatings).length === 0)', 1)[1].split('const prompts = getSummaryPrompts', 1)[0]
    assert 'await loadAiConfig();' in block
    assert '生成摘要前加载 AI 配置失败' in block


def test_ai_summary_loads_lightweight_contact_ratings_instead_of_full_contact_table():
    source = INDEX_HTML.read_text(encoding="utf-8")
    start = source.index("if (!contactRatings || Object.keys(contactRatings).length === 0)")
    end = source.index("const prompts = getSummaryPrompts", start)
    section = source[start:end]

    assert "await loadContactRatingsFromBackend();" in section
    assert "await loadContactsFromBackend();" not in section


def test_dasheng_member_settings_is_single_key_locked_preset():
    source = INDEX_HTML.read_text(encoding='utf-8')
    assert 'id="settings-dasheng-member"' not in source
    section = source.split('id="settings-ai-config"', 1)[1].split('id="settings-keyword-filter"', 1)[0]

    assert '大圣之怒会员设置' in section
    assert 'id="dashengUnifiedApiKey"' in section
    assert 'saveDashengMemberSettings()' in section
    assert 'restoreDashengDefaults()' in section
    assert 'name="aiProviderMode" value="dasheng"' in section
    assert 'name="aiProviderMode" value="custom"' in section
    assert 'id="aiCustomSettingsShell"' in section
    assert 'Provider' in section
    assert '大圣 Cloud（水木算力）' in section
    assert 'gpt-5.5' in section
    assert 'DeepSeek V4 Flash' in section
    assert 'MiniMax-M3' in section
    assert '多模态模型（一页通）' in section
    assert section.count('<input disabled') >= 6

    assert 'function saveDashengMemberSettings' in source
    assert 'function buildDashengMemberConfigBody' in source
    assert 'function applyAiProviderModeUi' in source
    assert 'function restoreDashengDefaults' in source
    assert 'settings-dasheng-member' not in source.split('const AI_SECTION_IDS = new Set([', 1)[1].split(']);', 1)[0]


def test_advanced_ai_save_does_not_force_dasheng_provider():
    source = INDEX_HTML.read_text(encoding='utf-8')
    block = source.split('async function saveApiConfig()', 1)[1].split('function getSendProvider()', 1)[0]

    assert 'validateRouterConfig(modelRouter)' in block
    assert 'api_url: DASHENG_CLOUD_API_URL' not in block
    assert 'api_key: unifiedKey' not in block
    assert 'has_key: preserveDashengKey' not in block


def test_onepage_export_prefers_image_generation_with_local_fallback():
    source = INDEX_HTML.read_text(encoding='utf-8')

    assert 'id="onepageOutputMode"' in source
    assert 'id="onepageImageModel"' in source
    assert 'id="onepageImageApiUrl"' in source
    assert 'id="onepageImageApiKey"' in source
    assert 'id="onepageImageSize"' in source
    assert 'id="onepageImageQuality"' in source
    assert 'function generateOnepageImage' in source
    assert "'/api/ai/onepage-image'" in source
    assert "'/api/ai/onepage-audio'" in source
    assert 'id="onepageAudio5Btn"' in source
    assert 'id="onepageAudio10Btn"' in source
    assert 'downloadOnepageImageResult' in source
    assert 'downloadOnepageAudioResult' in source
    assert 'buildOnepageMindMapNode' in source
    assert 'op-mindmap' in source
    assert 'onepageTextBudget' in source


def test_ai_analysis_toolbar_uses_compact_layout_labels():
    source = INDEX_HTML.read_text(encoding='utf-8')
    section = source.split('id="ai-summary"', 1)[1].split('class="summary-sections"', 1)[0]

    assert 'data-period="1day">一天<' in section
    assert 'data-period="3days">三天<' in section
    assert 'data-period="1week">七天<' in section
    assert 'data-period="1month">一月<' in section
    assert '近1天' not in section
    assert '近3天' not in section
    assert '近1周' not in section
    assert '近1月' not in section
    assert 'runAnalysisBtn" class="analysis-btn run-primary"' in section
    assert 'button-label">运行分析<' in section
    assert '分析模块：' not in section
    assert 'module-toggle' not in section
    assert 'id="analysisParamsInline"' in section
    assert '#analysisParamsInline {\n            display: none !important;' in source


def test_run_analysis_loads_recent_messages_when_ai_page_has_no_local_data():
    source = INDEX_HTML.read_text(encoding="utf-8")
    start = source.index("async function performAIAnalysis(")
    end = source.index("function _summaryReportFieldMap()", start)
    section = source[start:end]

    assert "await loadRecentMessagesFromBackend" in section
    assert section.index("await loadRecentMessagesFromBackend") < section.index("if (!filtered.length && !window.VibeDeskBridge")


def test_ai_summary_cards_use_generate_action_label():
    source = INDEX_HTML.read_text(encoding='utf-8')
    section = source.split('class="summary-sections"', 1)[1].split('id="settings"', 1)[0]

    assert section.count('data-action="retry"') == 8
    assert section.count('data-action="retry" data-module=') == 8
    assert section.count('>生成</button>') >= 8
    assert '>重试</button>' not in section
    assert "const map = { '1day': '一天', '3days': '三天', '1week': '七天', '1month': '一月' };" in source


def test_dashboard_surfaces_deeper_actionable_insights():
    source = INDEX_HTML.read_text(encoding='utf-8')
    section = source.split('id="dashboard"', 1)[1].split('id="ai-summary"', 1)[0]

    assert '情报驾驶舱' in section
    assert 'dashboardRangeSelect' in section
    assert 'dashboardRefreshBtn' in section
    assert 'dashboardBriefStack' in section
    assert '机会 / 风险雷达' in section
    assert 'dashboardOpportunityList' in section
    assert 'dashboardRiskList' in section
    assert '主题动量' in section
    assert 'dashboardMomentumList' in section
    assert 'dashboardActionStrip' in section
    assert 'Income Tracker' not in section
    assert 'Recent Signals' not in section
    assert 'Trend Keywords' not in section
    assert 'Proposal Progress' not in section

    assert 'function focusDashboardMessage' in source
    assert 'function bindDashboardDeepActions' in source
    assert 'data-dash-row-id' in source
    assert 'data-dash-sender' in source
    assert 'data-dash-query' in source
    assert 'opportunityWords' in source
    assert 'riskWords' in source
    assert 'topicMomentum' in source
    assert 'rangeDays * 2 - 1' in source


def test_send_management_layout_has_scenarios_and_hover_help():
    source = INDEX_HTML.read_text(encoding='utf-8')
    section = source.split('id="send-management"', 1)[1].split('id="contact-management"', 1)[0]

    assert 'sendScenarioStrip' in section
    assert 'data-send-scenario="bulk"' in section
    assert 'data-send-scenario="reply"' in section
    assert 'data-send-scenario="link"' in section
    assert 'data-send-scenario="mp"' in section
    assert '微信群发' in section
    assert '消息回复' in section
    assert '生成链接' in section
    assert '公众号卡片' in section
    assert 'sendScenarioNote' in section
    assert section.count('class="info-tip"') >= 7
    assert 'send-provider-note">支持拖拽/点击上传' not in section
    assert 'send-manager-subtitle' not in section

    assert '.info-tip::after' in source
    assert '#send-management .send-split { grid-template-columns: minmax(520px, 42vw) minmax(720px, 1fr);' in source
    assert '#send-management .send-contact-columns { grid-template-columns: minmax(104px,.55fr) minmax(190px,1.14fr) minmax(210px,1.28fr);' in source
    assert '#send-management .send-contact-item { display:grid;' in source
    assert 'const SEND_SCENARIO_META' in source
    assert 'function setSendScenario' in source
    assert 'function bindSendScenarioStrip' in source
    assert 'bindSendScenarioStrip();' in source


def test_send_management_supports_link_only_tasks_and_current_tag_index():
    source = INDEX_HTML.read_text(encoding='utf-8')

    assert 'tagBuckets.get' not in source
    assert 'Array.from(tagIndex.get(next) || [])' in source
    assert 'function taskHasSendableContent(t)' in source
    assert "'/api/send/link-preview'" not in source
    assert '/api/send/link-preview?url=${encodeURIComponent(url)}' in source
    assert "thumb_url: String(preview.thumb_url || '')" in source
    assert "desc: String(preview.desc || '')" in source
    assert 'async function addComposerLink()' in source

    render_tasks = source.split('function renderTasks()', 1)[1].split('async function generateTask', 1)[0]
    assert 'if (!taskHasSendableContent(t))' in render_tasks

    send_tasks = source.split('async function sendTasks', 1)[1].split('function attachToTasks', 1)[0]
    assert 'taskHasSendableContent(t)' in send_tasks
    assert "String(t.reply||'').trim() || String(document.getElementById('sendBulkText')" not in send_tasks

    batch_send = source.split("rebind('batchSendWX'", 1)[1].split("rebind('sendClearTasks'", 1)[0]
    assert batch_send.count('taskHasSendableContent(t)') >= 2


def test_reply_tasks_do_not_inherit_stale_composer_assets():
    source = INDEX_HTML.read_text(encoding="utf-8")
    start = source.index("function buildSendPayloadForTask(t)")
    end = source.index("function taskHasSendableContent(t)", start)
    section = source[start:end]

    assert "function taskUsesComposerAssets(t)" in source
    assert "const useComposerAssets = taskUsesComposerAssets(t);" in section
    assert "const links = useComposerAssets ? buildComposerLinks() : [];" in section
    assert "const uploads = useComposerAssets ? buildComposerUploads() : [];" in section

    send_start = source.index("async function sendTasks")
    send_end = source.index("function attachToTasks", send_start)
    send_section = source[send_start:send_end]
    assert "const useCampaignComposerAssets = toSend.every(taskUsesComposerAssets);" in send_section
    assert "content_parts: useCampaignComposerAssets ? buildComposerLinks() : []" in send_section
    assert "attachments: useCampaignComposerAssets ? buildComposerUploads() : []" in send_section


def test_reply_preview_updates_live_and_legacy_send_checks_wechatapi_result():
    source = INDEX_HTML.read_text(encoding="utf-8")

    render_start = source.index("function renderTasks()")
    render_end = source.index("async function generateTask", render_start)
    render_section = source[render_start:render_end]
    input_start = render_section.index("ta.addEventListener('input'")
    input_end = render_section.index("});", input_start)
    assert "renderSendPreview();" in render_section[input_start:input_end]
    empty_start = render_section.index("if (!visible.length)")
    empty_end = render_section.index("return;", empty_start)
    assert "renderSendPreview();" in render_section[empty_start:empty_end]
    append_start = render_section.index("body.appendChild(frag);")
    assert "renderSendPreview();" in render_section[append_start:]

    assert "sendToN8nWorkflow" not in source
    assert "async function sendThroughWechatApi(sendItem)" in source
    send_start = source.index("async function sendThroughWechatApi(sendItem)")
    send_end = source.index("// 发送管理功能", send_start)
    send_section = source[send_start:send_end]
    assert "data?.result?.results" in send_section
    assert "result?.ok === false" in send_section
    assert "data?.status !== 'done'" in send_section


def test_header_freshness_prefers_realtime_message_time_over_stale_chatlog_sync():
    source = INDEX_HTML.read_text(encoding="utf-8")
    start = source.index("async function updateInfoStatistics(messages)")
    end = source.index("function updateMarketOpinions", start)
    section = source[start:end]

    assert "const latestMessageTime" in section
    assert "let lastSync = latestMessageTime;" in section
    assert "if (!lastSync)" in section
    assert "lastSync = s.last_sync || '';" in section
    assert "<span>更新 ${toTime(lastSync)}</span>" in section


def test_lazy_cached_lists_stay_visible_during_background_refresh():
    source = INDEX_HTML.read_text(encoding='utf-8')
    assert 'function renderLoadingIfNoCached' in source
    assert "显示上次内容，后台更新中…" in source
    assert "显示上次消息，后台更新中..." in source
    folo_block = source.split('async function refreshFolo()', 1)[1].split('async function refreshMpAgg()', 1)[0]
    assert "const cachedShown = showCachedList('folo-agg'" in folo_block
    assert 'renderLoadingIfNoCached(tbody, cachedShown, 12)' in folo_block
    assert 'if (!cachedShown) tbody.innerHTML' in folo_block
    mp_block = source.split('async function refreshMpAgg()', 1)[1].split('// legacy render path retained unreachable for safety', 1)[0]
    assert "const cachedShown = showCachedList('mp-agg'" in mp_block
    assert 'renderLoadingIfNoCached(tbody, cachedShown, 9)' in mp_block
    minutes_block = source.split('async function loadMinutes(refresh=false)', 1)[1].split('function updateMinutesDisplay()', 1)[0]
    assert "const cachedShown = showCachedList('minutes-agg'" in minutes_block
    assert 'renderLoadingIfNoCached(tbody, cachedShown, 9)' in minutes_block
    messages_block = source.split('async function loadRecentMessagesFromBackend', 1)[1].split('const now = new Date();', 1)[0]
    assert "cachedShown = showCachedList('message-list'" in messages_block
    assert 'if (!cachedShown) showMessageTableLoading();' in messages_block


def test_deeppupil_chinese_brand_is_visually_bold():
    source = INDEX_HTML.read_text(encoding='utf-8')
    block = source.split('.brand-name {', 1)[1].split('}', 1)[0]
    assert 'font-weight: 1000;' in block
    assert 'font-size: 34px;' in block
    assert '-webkit-text-stroke: .45px #000;' in block
    assert 'transform: scaleX(1.04);' in block
