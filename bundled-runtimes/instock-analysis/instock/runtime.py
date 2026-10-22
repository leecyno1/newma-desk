"""Standalone analysis process; Desk is an optional HTTP host, not a source import."""

import argparse
import os
from pathlib import Path
from urllib.parse import urlsplit


def validate_market_services_url(value):
    url = urlsplit(value)
    if (url.scheme not in {"http", "https"} or not url.hostname
            or url.username or url.password or url.path not in {"", "/"}
            or url.query or url.fragment):
        raise ValueError("基础数据服务须为不含路径、凭据、查询参数或片段的 HTTP(S) origin")
    return value.rstrip("/")


def configure_runtime(args, environ=None):
    env = os.environ if environ is None else environ
    from instock.web.analysis_scope import desk_session_required, validate_scope_url
    required = desk_session_required(env)
    scope_url = env.get("INSTOCK_DESK_SCOPE_URL", "").strip()
    if scope_url:
        validate_scope_url(scope_url)
    elif required:
        raise ValueError("仅 Desk 会话模式必须配置 INSTOCK_DESK_SCOPE_URL")
    data_url = args.data_url or env.get("INSTOCK_DATA_URL") or env.get("NEWMA_DESK_DATA_URL")
    if not data_url:
        raise ValueError("请用 --data-url 或 INSTOCK_DATA_URL 配置兼容的数据接口；未自动连接本机 Desk")
    url = urlsplit(data_url)
    if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError("数据接口须为不含凭据、查询参数或片段的 HTTP(S) URL")
    if not 1 <= args.port <= 65535:
        raise ValueError("端口必须位于 1 到 65535")
    market_services_url = getattr(args, "market_services_url", None) or env.get("INSTOCK_MARKET_SERVICES_URL")
    if market_services_url:
        market_services_url = validate_market_services_url(market_services_url)
    state_root = args.state_dir or env.get("INSTOCK_STATE_DIR")
    if not state_root:
        state_root = str(Path(env.get("XDG_STATE_HOME") or Path.home() / ".local/state") / "instock-analysis")
    state = Path(state_root).expanduser().resolve()
    env["INSTOCK_SKIP_DB"] = "1"
    env["INSTOCK_RUNTIME_MODE"] = "newma-desk-attached" if getattr(args, "mode", "standalone") == "desk" else "standalone"
    env["INSTOCK_WEB_HOST"] = args.host
    env["INSTOCK_WEB_PORT"] = str(args.port)
    env["INSTOCK_MARKET_DATA_PROVIDER"] = "http"
    env["INSTOCK_DATA_URL"] = data_url.rstrip("/")
    if market_services_url:
        env["INSTOCK_MARKET_SERVICES_URL"] = market_services_url
    env["INSTOCK_STATE_DIR"] = str(state)
    for key, name in {
        "INSTOCK_ANALYSIS_HISTORY_DB_PATH": "analysis_history.sqlite3",
        "INSTOCK_SECTOR_FUND_FLOW_DB_PATH": "sector_fund_flow.sqlite3",
        "INSTOCK_ROTATION_SHADOW_DB_PATH": "rotation_shadow_state.sqlite3",
    }.items():
        # Existing databases stay where their operator configured them.
        env.setdefault(key, str(state / name))
    log_root = getattr(args, "log_dir", None)
    env.setdefault("INSTOCK_LOG_DIR", str(Path(log_root).expanduser().resolve() if log_root else state / "logs"))
    return state


def main(argv=None):
    parser = argparse.ArgumentParser(description="InStock 独立研究服务（无 MySQL；数据通过 HTTP 接口配置）")
    parser.add_argument("--mode", choices=["standalone", "desk"], default="standalone",
                        help="进程生命周期归属；不授予 Agent 或嵌入会话权限")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9988)
    parser.add_argument("--data-url", help="兼容研究数据接口，如 http://127.0.0.1:8911/api/research")
    parser.add_argument("--market-services-url", help="交易日历、成交价和市场结构等基础服务的 HTTP(S) origin")
    parser.add_argument("--state-dir", help="本机运行数据目录；不会迁移旧数据库")
    parser.add_argument("--log-dir", help="默认日志位置；保留显式 INSTOCK_LOG_DIR")
    args = parser.parse_args(argv)
    try:
        configure_runtime(args)
    except ValueError as error:
        parser.error(str(error))
    # Import only after paths and HTTP-only mode are set.
    from instock.web.web_service import main as serve
    serve()


if __name__ == "__main__":
    main()
