#!/usr/bin/env bash
# =============================================================================
# 0913 WeChat Automation Platform — One-Click Deploy Script
# =============================================================================
# Usage: bash deploy-0913.sh [install_dir]
# Default install_dir: /opt/0913
#
# What this does:
# 1. Clone / copy the 0913 repo
# 2. Install Python dependencies
# 3. Prompt for credentials (wechatapi token, AI keys, callback URL)
# 4. Generate .env and ai_config.json from templates
# 5. Initialize the database
# 6. Start the service
# 7. Bind wechatapi callback
# 8. Verify health + auto-reply chain
# =============================================================================

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[✓]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
err()   { echo -e "${RED}[✗]${NC} $*"; }

INSTALL_DIR="${1:-/opt/0913}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "============================================"
echo "  0913 WeChat Automation Platform Deploy"
echo "============================================"
echo ""

# ── Step 1: Copy source ──
info "Step 1/8: Setting up source at ${INSTALL_DIR}"
if [ -f "${SCRIPT_DIR}/../app/main.py" ]; then
    mkdir -p "${INSTALL_DIR}"
    rsync -a --exclude='data/app.db' --exclude='data/app.db.*' --exclude='__pycache__' --exclude='*.pyc' --exclude='.env' --exclude='uvicorn.log' "${SCRIPT_DIR}/../" "${INSTALL_DIR}/"
    info "Copied from ${SCRIPT_DIR}/.."
else
    warn "No local source found. Clone from git repo? (y/n)"
    read -r clone_ans
    if [ "$clone_ans" = "y" ]; then
        echo -n "Git URL: "; read -r git_url
        git clone "$git_url" "${INSTALL_DIR}"
    else
        err "No source available. Abort."
        exit 1
    fi
fi
cd "${INSTALL_DIR}"

# ── Step 2: Install dependencies ──
info "Step 2/8: Installing Python dependencies"
if ! command -v python3 &>/dev/null; then
    err "python3 not found. Install Python 3.11+ first."
    exit 1
fi
python3 -m venv venv 2>/dev/null || true
source venv/bin/activate 2>/dev/null || true
pip install -q -r requirements.txt 2>&1 | tail -1
info "Dependencies installed"

# ── Step 3: Credentials ──
info "Step 3/8: Configuring credentials"
echo ""
echo "=== WeChat API Gateway ==="
echo -n "  wechatapi token (VideosApi-token): "; read -r WX_TOKEN
echo -n "  wechatapi app_id: "; read -r WX_APP_ID
echo -n "  Callback public URL (e.g. https://your-tunnel/api/wechat-gateway/callback): "; read -r CALLBACK_URL

echo ""
echo "=== AI / LLM API Keys ==="
echo -n "  SiliconFlow API key (for summaries/fallback): "; read -r SF_KEY
echo -n "  MiniMax API key (for WeChat auto-reply route): "; read -r MM_KEY

echo ""
echo "=== Other ==="
echo -n "  API Token (for frontend auth): "; read -r API_TOKEN
echo -n "  Chatlog HTTP base (default: http://127.0.0.1:5030): "; read -r CHATLOG_HTTP
CHATLOG_HTTP="${CHATLOG_HTTP:-http://127.0.0.1:5030}"
echo -n "  Chatlog dir path: "; read -r CHATLOG_DIR

# ── Step 4: Generate configs ──
info "Step 4/8: Generating config files"

# .env
cat > .env <<EOF
CHATLOG_HTTP_BASE=${CHATLOG_HTTP}
CHATLOG_DIR=${CHATLOG_DIR}
API_TOKEN=${API_TOKEN}
AGENT_API_TOKEN=${API_TOKEN}
DATABASE_URL=sqlite:///./data/app.db
MEDIA_SERVER_BASE=http://127.0.0.1:8001
HOST=127.0.0.1
PORT=8001
SYNC_INTERVAL_SECONDS=0
NEWSNOW_REFRESH_INTERVAL_SECONDS=3600
AI_MAX_PARALLEL=12
SILICONFLOW_API_KEY=${SF_KEY}
SILICONFLOW_API_URL=https://api.siliconflow.cn/v1
MINIMAX_API_KEY=${MM_KEY}
EOF
info ".env generated"

# ai_config.json from template
if [ -f "data/ai_config.json.example" ]; then
    cp data/ai_config.json.example data/ai_config.json
    # Inject keys
    if command -v python3 &>/dev/null; then
        python3 -c "
import json
c = json.load(open('data/ai_config.json'))
c['api_key'] = '${SF_KEY}'
for ch in c.get('model_router',{}).get('tool_channels',[]):
    if ch.get('id') == 'tool-minimax-cn-m27':
        ch['api_key'] = '${MM_KEY}'
json.dump(c, open('data/ai_config.json','w'), indent=2, ensure_ascii=False)
"
    fi
    info "ai_config.json generated"
else
    warn "data/ai_config.json.example not found — using defaults"
fi

# ── Step 5: Init DB ──
info "Step 5/8: Initializing database"
mkdir -p data
python3 -c "
from app.db import Base, engine
Base.metadata.create_all(bind=engine)
print('DB initialized')
"
info "Database initialized"

# ── Step 6: Seed gateway config ──
info "Step 6/8: Seeding WeChat gateway config"
python3 -c "
import json
from app.db import SessionLocal
from app.models import SyncState, WechatSubsession

db = SessionLocal()
try:
    # Gateway config
    gw = {
        'enabled': True, 'outbound_enabled': True,
        'sessionized_reply_enabled': True, 'fixed_subsession_enabled': True,
        'fixed_subsession_id': 'wechat_gateway_default', 'fixed_subsession_name': '微信工作流分身',
        'base_url': 'http://api.wechatapi.net/finder/v2/api', 'header_name': 'VideosApi-token',
        'token': '${WX_TOKEN}', 'app_id': '${WX_APP_ID}',
        'callback_path': '/api/wechat-gateway/callback', 'callback_public_url': '${CALLBACK_URL}',
        'device_type': 'ipad', 'region_id': '11000',
    }
    r = db.get(SyncState, 'wechat_gateway_config')
    if r: r.value = json.dumps(gw, ensure_ascii=False)
    else: db.add(SyncState(key='wechat_gateway_config', value=json.dumps(gw, ensure_ascii=False)))

    # Trigger rules
    tr = {
        'enabled': True, 'smart_reply_enabled': True, 'group_enabled': True, 'private_enabled': True,
        'prefixes': ['ai'], 'regexp_patterns': [], 'at_mention_enabled': False, 'random_rate': 0,
        'min_text_length': 2, 'human_reply_suppression_seconds': 20,
        'private_wakeup_window_seconds': 180, 'private_wakeup_whitelist_enabled': False,
        'private_wakeup_whitelist_chat_ids': [], 'private_wakeup_exit_commands': ['暂停'],
    }
    r = db.get(SyncState, 'wechat_gateway_trigger_rules')
    if r: r.value = json.dumps(tr, ensure_ascii=False)
    else: db.add(SyncState(key='wechat_gateway_trigger_rules', value=json.dumps(tr, ensure_ascii=False)))

    # Subsession
    sub = db.get(WechatSubsession, 'wechat_gateway_default')
    if not sub:
        db.add(WechatSubsession(
            id='wechat_gateway_default', channel='wechat_gateway', name='微信工作流分身',
            enabled=True, mode='fixed',
            system_prompt='你是微信工作流分身,叫柠檬博士，是主Agent的投资助理，你会接收到大量券商/基金/研究所的消息，你的回复简洁、专业、数据说话、沉稳幽默，简洁精炼、段落清晰：\\n#规范#\\n-路演/会议/调研/电话邀约：对方联系人一般会附带8-10位的数字号码，这类回复已知晓，无需肯定/否定和明确意见\\n-市场观点、策略建议、行业研究、个股研究：分析文本，并结合你的知识、网络搜索、数据库进行思考判断，针对有价值的信息（如推荐买入，卖出，提示风险，市场判断等）进行追问和讨论；\\n-派点、打分等请求：礼貌回复尽力支持，提示让对方销售联系公司添加服务记录\\n-对方发问：对方针对当前市场、经济、股票或某只基金提问时，要根据你的知识、网络搜索、数据库进行思考判断，引用数据、严谨回复答案\\n#',
            model_route_kind='tool', model_route_key='reply',
            history_max_messages=66, history_max_tokens=8192,
            allow_cross_chat_context=True, allow_cross_sender_context=True,
        ))
    db.commit()
    print('Gateway config seeded')
finally:
    db.close()
"
info "Gateway config seeded"

# ── Step 7: Start service ──
info "Step 7/8: Starting service"
bash scripts/manage.sh start 2>&1 || true
sleep 3

# ── Step 8: Verify ──
info "Step 8/8: Verifying deployment"

# Health check
HEALTH=$(curl -sf http://127.0.0.1:8001/api/health 2>/dev/null || echo "FAIL")
if echo "$HEALTH" | grep -q '"ok"'; then
    info "Health check: OK"
else
    err "Health check failed: ${HEALTH}"
fi

# Bind callback
BIND=$(curl -sf -X POST http://127.0.0.1:8001/api/wechat-gateway/bind-callback 2>/dev/null || echo "FAIL")
if echo "$BIND" | grep -q '"ok"'; then
    info "Callback binding: OK"
else
    warn "Callback binding failed (may need manual binding after tunnel is set up): ${BIND}"
fi

echo ""
echo "============================================"
echo "  Deployment Complete!"
echo "============================================"
echo ""
echo "  Service:  http://127.0.0.1:8001"
echo "  Config:   ${INSTALL_DIR}/.env"
echo "  AI Config: ${INSTALL_DIR}/data/ai_config.json"
echo "  Logs:     ${INSTALL_DIR}/uvicorn.log"
echo ""
echo "  Next steps:"
echo "  1. Set up public tunnel (ngrok/natapp/frp) to expose :8001"
echo "  2. Visit http://127.0.0.1:8001 to access the dashboard"
echo "  3. Go to WeChat settings tab, verify callback URL, click 'Bind Callback'"
echo "  4. Test: send 'ai hello' to your WeChat"
echo ""
