"""审计修复回归测（2026-07-05，全部离线）：
鉴权中间件 / 持仓 CRUD 与坏文件降级 / 估值脏数据防护 / 涨停池脏数值 /
空结果不缓存 / akshare 缺失降级 / 无 index 工具调用归位 / CLI 流式超时。
"""
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

import app as app_module
import astock
import chat
import cli_runtime
import market
import portfolio as pf

client = TestClient(app_module.app)


# ── VR_API_KEY 鉴权中间件 ───────────────────────────────────────────

def test_api_key_auth(monkeypatch):
    monkeypatch.setattr(app_module, "_API_KEY", "sekret")
    assert client.get("/api/health").status_code == 200  # health 豁免
    assert client.get("/api/quote?codes=abc").status_code == 401  # 缺头
    assert client.get("/api/quote?codes=abc", headers={"Authorization": "Bearer wrong"}).status_code == 401
    # 正确 key → 通过鉴权、走到参数校验层（400 而非 401，不联网）
    assert client.get("/api/quote?codes=abc", headers={"Authorization": "Bearer sekret"}).status_code == 400


# ── 持仓：本地 JSON CRUD（不联网，行情打桩） ────────────────────────

@pytest.fixture()
def tmp_pf(tmp_path, monkeypatch):
    monkeypatch.setattr(pf, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(pf, "PF_FILE", str(tmp_path / "portfolio.json"))
    monkeypatch.setattr(astock, "tencent_quote", lambda codes: {c: {"name": f"股{c}", "price": 10.0} for c in codes})
    return tmp_path


def test_portfolio_crud_roundtrip(tmp_pf):
    assert client.get("/api/portfolio").json()["data"]["holdings"] == []

    r = client.post("/api/portfolio/holding", json={"code": "600519", "shares": 100, "cost": 8.0})
    assert r.status_code == 200
    h = r.json()["data"]["holdings"][0]
    assert h["code"] == "600519"
    assert h["pnl"] == pytest.approx((10.0 - 8.0) * 100)

    # 同代码加仓 → 加权平均成本
    client.post("/api/portfolio/holding", json={"code": "600519", "shares": 100, "cost": 12.0})
    h = client.get("/api/portfolio").json()["data"]["holdings"][0]
    assert h["shares"] == 200
    assert h["cost"] == pytest.approx(10.0)

    r = client.post("/api/portfolio/close", json={"code": "600519", "date": "2026-07-05", "price": 11.0, "shares": 200, "cost": 10.0})
    assert r.status_code == 200
    assert r.json()["data"]["closed"][0]["pnl"] == pytest.approx(200.0)

    assert client.delete("/api/portfolio/holding?code=600519").json()["data"]["holdings"] == []
    assert client.delete("/api/portfolio/close?index=0").json()["data"]["closed"] == []
    assert client.post("/api/portfolio/refresh").status_code == 200


def test_portfolio_add_validation(tmp_pf):
    assert client.post("/api/portfolio/holding", json={"code": "abc", "shares": 1, "cost": 1}).status_code == 400
    assert client.post("/api/portfolio/holding", json={"code": "600519", "shares": 0, "cost": 1}).status_code == 400


def test_portfolio_corrupt_file_returns_empty(tmp_pf):
    (tmp_pf / "portfolio.json").write_text("{broken json", encoding="utf-8")
    r = client.get("/api/portfolio")
    assert r.status_code == 200
    assert r.json()["data"]["holdings"] == []


# ── issue #13：加仓合并成本保留 4 位小数（ETF/基金成本常见 3-4 位） ──

def test_portfolio_merge_cost_keeps_4_decimals(tmp_pf):
    client.post("/api/portfolio/holding", json={"code": "510300", "shares": 100, "cost": 1.0001})
    client.post("/api/portfolio/holding", json={"code": "510300", "shares": 100, "cost": 1.0003})
    h = client.get("/api/portfolio").json()["data"]["holdings"][0]
    assert h["cost"] == pytest.approx(1.0002, abs=1e-9)


# ── issue #12：旧版数据在仓库内 .cache/，重下载会丢 → 自动迁到用户目录 ──

def test_portfolio_legacy_migration(tmp_path, monkeypatch):
    old = tmp_path / "repo-cache" / "portfolio.json"
    old.parent.mkdir()
    old.write_text('{"holdings": [{"code": "600519", "shares": 100, "cost": 8.0}]}', encoding="utf-8")
    monkeypatch.setattr(pf, "_OLD_PF_FILE", str(old))
    monkeypatch.setattr(pf, "CACHE_DIR", str(tmp_path / "userdata"))
    monkeypatch.setattr(pf, "PF_FILE", str(tmp_path / "userdata" / "portfolio.json"))
    pf._migrate_legacy()
    assert pf._load()["holdings"][0]["code"] == "600519"
    # 新位置已有数据 → 再跑迁移不覆盖
    pf._save({"holdings": []})
    pf._migrate_legacy()
    assert pf._load()["holdings"] == []


def test_myreports_legacy_migration(tmp_path, monkeypatch):
    import myreports as mr

    old = tmp_path / "repo-cache" / "myreports"
    old.mkdir(parents=True)
    (old / "index.json").write_text("[]", encoding="utf-8")
    monkeypatch.delenv("VR_REPORTS_DIR", raising=False)
    monkeypatch.setattr(mr, "_OLD_DEFAULT_DIR", old)
    monkeypatch.setattr(mr, "REPORTS_DIR", tmp_path / "userdata" / "myreports")
    # 上次复制中断留下的半截临时目录，不该挡住这次迁移
    stale = tmp_path / "userdata" / "myreports.migrate.tmp"
    stale.mkdir(parents=True)
    (stale / "partial.bin").write_text("x", encoding="utf-8")
    mr._migrate_legacy()
    dst = tmp_path / "userdata" / "myreports"
    assert (dst / "index.json").exists()
    assert not (dst / "partial.bin").exists()  # 半截内容没混进正式目录


# ── full_valuation：一致预期缺「均值」/ '-' 占位不再 502 ─────────────

_QUOTE = {"600519": {"name": "贵州茅台", "price": 100.0, "mcap_yi": 1000, "pe_ttm": 20.0, "pb": 5.0}}


def test_full_valuation_dirty_forecast(monkeypatch):
    monkeypatch.setattr(astock, "tencent_quote", lambda codes: _QUOTE)
    monkeypatch.setattr(astock, "profit_forecast", lambda code: [
        {"年度": "2026", "预测机构数": "-"},  # 缺「均值」+ 脏机构数
        {"年度": "2027", "均值": "-"},        # '-' 占位
    ])
    out = astock.full_valuation("600519")
    assert out["eps_26e"] is None
    assert out["eps_27e"] is None
    assert out["pe_26e"] is None


def test_full_valuation_string_numbers(monkeypatch):
    monkeypatch.setattr(astock, "tencent_quote", lambda codes: _QUOTE)
    monkeypatch.setattr(astock, "profit_forecast", lambda code: [
        {"年度": "2026年", "均值": "2.0", "预测机构数": "12"},
        {"年度": "2027年", "均值": 2.4},
    ])
    out = astock.full_valuation("600519")
    assert out["eps_26e"] == 2.0
    assert out["analyst_count"] == 12
    assert out["pe_26e"] == 50.0


# ── 短线情绪：涨停池脏数值（'-' 占位）不再让排序崩溃 ────────────────

def test_emotion_dirty_amount(monkeypatch):
    pools = {
        "getTopicZTPool": [
            {"c": "600001", "n": "甲", "lbc": 3, "p": 10000, "zdp": 10.0, "amount": "-", "ltsz": None, "hybk": "X"},
            {"c": "600002", "n": "乙", "lbc": 2, "p": "-", "zdp": None, "amount": 5e8, "ltsz": 1e9, "hybk": "Y"},
        ],
        "getTopicZBPool": [],
        "getTopicDTPool": [],
        "getYesterdayZTPool": [{}],
    }
    monkeypatch.setattr(astock, "em_zt_topic_pool", lambda ep, d, sort="": pools.get(ep, []))
    out = market._emotion()
    stocks = out["lianban_stocks"]
    assert [s["code"] for s in stocks] == ["600001", "600002"]  # 排序没崩、按连板数降序
    assert stocks[0]["amount"] is None    # '-' 归一为 None
    assert stocks[1]["price"] == 0.0      # p='-' 归一后按 0 展示
    assert stocks[1]["amount"] == 5e8


# ── 缓存：数据源故障的空结果不缓存 5 分钟 ───────────────────────────

def test_cached_skips_empty():
    market._CACHE.pop("k_test", None)
    calls = []

    def flaky():
        calls.append(1)
        return {} if len(calls) == 1 else {"ok": 1}

    assert market._cached("k_test", flaky) == {}
    assert market._cached("k_test", flaky) == {"ok": 1}  # 空结果没被缓存 → 下次重试成功
    assert market._cached("k_test", flaky) == {"ok": 1}  # 非空已缓存，不再调用
    assert len(calls) == 2
    market._CACHE.pop("k_test", None)


# ── akshare 未安装：market 降级返回空，不挡服务 ─────────────────────

def test_market_degrades_without_akshare(monkeypatch):
    def boom():
        raise astock.DependencyMissing("akshare 未安装")

    monkeypatch.setattr(astock, "_akshare", boom)
    assert market._sentiment() == {}
    assert market._sectors() == []


def test_akshare_adapter_serializes_native_runtime_calls(monkeypatch):
    state = {"active": 0, "max_active": 0}
    state_lock = threading.Lock()

    class FakeAkshare:
        @staticmethod
        def probe(value):
            with state_lock:
                state["active"] += 1
                state["max_active"] = max(state["max_active"], state["active"])
            time.sleep(0.01)
            with state_lock:
                state["active"] -= 1
            return value

    monkeypatch.setattr(astock, "_akshare", lambda: FakeAkshare)
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert list(pool.map(
            lambda value: astock.akshare_call("probe", value),
            range(16),
        )) == list(range(16))

    assert state["max_active"] == 1


def test_akshare_adapter_uses_thread_only_tqdm_lock(monkeypatch):
    configured = []

    class FakeTqdm:
        @staticmethod
        def set_lock(lock):
            configured.append(lock)

    monkeypatch.setattr(astock, "_TQDM_LOCK_CONFIGURED", False)
    astock._configure_tqdm_for_threaded_runtime(FakeTqdm)
    astock._configure_tqdm_for_threaded_runtime(FakeTqdm)

    assert configured == [astock._TQDM_THREAD_LOCK]
    assert configured[0].__class__.__module__ == "_thread"


def test_parallel_akshare_adapter_only_allows_audited_http_functions(monkeypatch):
    class FakeAkshare:
        @staticmethod
        def macro_china_pmi_yearly():
            return "pmi"

        @staticmethod
        def probe():
            return "unsafe"

    monkeypatch.setattr(astock, "_akshare", lambda: FakeAkshare)

    assert astock.akshare_parallel_call("macro_china_pmi_yearly") == "pmi"
    with pytest.raises(ValueError, match="not approved"):
        astock.akshare_parallel_call("probe")


# ── 流式工具调用：非标网关不带 index 时按 id 归位、不串参数 ──────────

def test_stream_tool_calls_without_index(monkeypatch):
    deltas_rounds = [
        [  # 第一轮：增量全部不带 index —— 续块无 id、新调用带新 id
            {"tool_calls": [{"id": "call_a", "function": {"name": "query_quote", "arguments": '{"codes":'}}]},
            {"tool_calls": [{"function": {"arguments": '["600519"]}'}}]},
            {"tool_calls": [{"id": "call_b", "function": {"name": "query_news", "arguments": '{"code":"600519"}'}}]},
        ],
        [{"content": "答案"}],  # 第二轮：纯文本收尾
    ]
    state = {"round": 0}
    monkeypatch.setattr(chat, "_call_llm_stream", lambda cfg, messages, use_tools: None)

    def fake_iter(_resp):
        i = state["round"]
        state["round"] += 1
        yield from deltas_rounds[i]

    monkeypatch.setattr(chat, "_iter_sse_deltas", fake_iter)
    executed = []
    monkeypatch.setattr(chat, "_exec_tool", lambda name, args: (executed.append((name, args)), {"ok": 1})[1])

    events = list(chat.run_chat_stream(
        {"baseURL": "http://x", "apiKey": "k", "model": "m"},
        [{"role": "user", "content": "q"}],
    ))
    assert ("query_quote", {"codes": ["600519"]}) in executed  # 参数没被串坏
    assert ("query_news", {"code": "600519"}) in executed      # 两个调用各归各槽
    assert events[-1]["type"] == "done"


# ── CLI 流式：子进程挂起时超时真正生效（不再无限期阻塞） ────────────

def test_run_cli_stream_timeout(monkeypatch):
    monkeypatch.setattr(cli_runtime, "_CLI_TIMEOUT_S", 1)
    monkeypatch.setitem(cli_runtime._CLI_DEFS, "fake", {
        "bins": ["python3"],
        "delivery": "stdin",
        "build_args": lambda _: ["-c", "import time\nprint('x', flush=True)\ntime.sleep(30)"],
        "env": {},
    })
    chunks = []
    with pytest.raises(RuntimeError, match="超时"):
        for line in cli_runtime.run_cli_stream("fake", "s", "u"):
            chunks.append(line)
    assert chunks and chunks[0].strip() == "x"  # 挂起前的输出已正常流出
