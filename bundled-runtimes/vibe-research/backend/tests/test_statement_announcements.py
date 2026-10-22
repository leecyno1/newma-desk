from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
import requests
from fastapi.testclient import TestClient
import app
import astock


class Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 10, 20, tzinfo=tz)


def announcement(title, number='1225499406', code='300502', date='2026-08-25'):
    stamp = datetime.fromisoformat(date).replace(tzinfo=ZoneInfo('Asia/Shanghai')).timestamp() * 1000
    return {'secCode':code, 'secName':'示例公司', 'announcementId':number,
            'announcementTitle':title, 'announcementTime':stamp}


def mock_source(monkeypatch, payload, code='300502'):
    calls=[]
    monkeypatch.setattr(astock, 'datetime', Clock)
    monkeypatch.setattr(requests, 'get', lambda *a, **k: SimpleNamespace(raise_for_status=lambda:None,
        json=lambda:{'stockList':[{'code':code,'orgId':'org-test'}]}))
    def post(url, **kwargs):
        assert url == 'https://www.cninfo.com.cn/new/hisAnnouncement/query'
        calls.append(kwargs['data'])
        return SimpleNamespace(raise_for_status=lambda:None,json=lambda:payload)
    monkeypatch.setattr(requests, 'post', post)
    return calls


def test_recent_full_reports_preserve_versions_and_query_boundary(monkeypatch):
    calls=mock_source(monkeypatch, {'totalAnnouncement':40,'announcements':[
        announcement('2026年半年度报告'),
        announcement('2026年半年度报告摘要','1225499405'),
        announcement('关于2026年半年度报告披露的提示性公告','1225499412'),
        announcement('2026年半年度报告（更新后）','1225499500',date='2026-09-01'),
    ]})
    result=astock.statement_announcements('300502')
    assert [row['announcementId'] for row in result['items']]==['1225499500','1225499406']
    assert all(row['periodEnd']=='2026-06-30' for row in result['items'])
    assert result['hasMore'] and '非全历史' in result['boundary']
    assert calls[0]['seDate']=='2025-10-20~2026-10-20'
    assert calls[0]['column']=='szse' and calls[0]['stock']=='300502,org-test'
    assert calls[0]['searchkey']=='年度报告'


@pytest.mark.parametrize('code', ['600519','300502','920001'])
def test_legacy_disclosure_uses_current_dates_for_all_mainland_exchanges(monkeypatch,code):
    calls=mock_source(monkeypatch, {'totalAnnouncement':1,'announcements':[announcement('公告',code=code)]},code=code)
    rows=astock.disclosure(code)
    assert rows[0]['代码']==code and rows[0]['公告时间']=='2026-08-25'
    assert set(rows[0])=={'代码','简称','公告标题','公告时间','公告链接'}
    assert calls[0]['seDate'].endswith('2026-10-20')


def test_company_prefix_without_colon_keeps_full_reports_not_english_or_summary(monkeypatch):
    mock_source(monkeypatch, {'totalAnnouncement':5, 'announcements':[
        announcement('示例公司2026年半年度报告'),
        announcement('示例公司：2025年年度报告','1225114741'),
        announcement('示例公司2025年年度报告（英文版）','1225114733'),
        announcement('示例公司2026年半年度报告摘要','1225499405'),
        announcement('关于示例公司2026年半年度报告的提示','1225499412'),
    ]})
    result = astock.statement_announcements('300502')
    assert [row['announcementId'] for row in result['items']] == ['1225499406','1225114741']
    assert '中文' in result['boundary']


@pytest.mark.parametrize('payload', [
    {'totalAnnouncement':2,'announcements':None},
    {'totalAnnouncement':1,'announcements':[announcement('2026年半年度报告',code='600519')]},
    {'totalAnnouncement':1,'announcements':[announcement('2023年年度报告',date='2024-04-30')]},
])
def test_invalid_source_is_not_reported_as_no_disclosures(monkeypatch,payload):
    mock_source(monkeypatch,payload)
    with pytest.raises(astock.AnnouncementSourceUnavailable): astock.statement_announcements('300502')


def test_empty_query_and_read_only_route(monkeypatch):
    mock_source(monkeypatch,{'totalAnnouncement':0,'announcements':None})
    client=TestClient(app.app)
    response=client.get('/api/equity-research/statement-announcements',params={'code':'300502'})
    assert response.status_code==200 and response.json()['data']['items']==[]
    assert response.json()['data']['hasMore'] is False
    assert client.get('/api/equity-research/statement-announcements',params={'code':'bad'}).status_code==422
