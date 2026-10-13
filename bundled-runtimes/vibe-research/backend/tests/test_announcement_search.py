from types import SimpleNamespace
import pytest
import requests
from fastapi.testclient import TestClient
import app as app_module
import astock


def test_search_passes_disclosure_window_category_and_page(monkeypatch):
    seen=[]
    def get(url, **kwargs):
        seen.append(kwargs['params'])
        return SimpleNamespace(raise_for_status=lambda:None,json=lambda:{'success':1,'data':{
            'total_hits':21,'list':[{'art_code':'AN202608141827994407','notice_date':'2026-08-15 00:00:00','title':'半年报更正公告','columns':[]}],
        }})
    monkeypatch.setattr(requests,'get',get)
    result=astock.announcement_search('600519','2026-06-30','2026-09-17','financial',2)
    assert seen[0]['begin_time']=='2026-06-30' and seen[0]['end_time']=='2026-09-17'
    assert seen[0]['f_node']==1 and seen[0]['page_index']==2 and seen[0]['page_size']==20
    assert result['page']==2 and result['total']==21 and result['hasMore'] is False
    assert result['items'][0]['date']=='2026-08-15'
    # Existing consumers still get the recent-list array, with no date filter.
    assert isinstance(astock.announcements('600519'),list)
    assert seen[1]['page_size']==15 and seen[1]['f_node']==0
    assert 'begin_time' not in seen[1]


@pytest.mark.parametrize('payload', [{'success':0,'data':{'list':[]}}, {'success':1,'data':{}}])
def test_source_failure_is_not_a_zero_result(monkeypatch,payload):
    monkeypatch.setattr(requests,'get',lambda *a,**kw:SimpleNamespace(raise_for_status=lambda:None,json=lambda:payload))
    with pytest.raises(ValueError):astock.announcement_search('600519','2026-06-30','2026-09-17')


def test_route_validates_dates_and_preserves_search_parameters(monkeypatch):
    calls=[]
    def search(*args):
        calls.append(args)
        return {'items':[],'page':args[-1],'total':0}
    monkeypatch.setattr(astock,'announcement_search',search)
    client=TestClient(app_module.app)
    query={'code':'600519','begin':'2026-06-30','end':'2026-09-17','category':'all','page':2}
    assert client.get('/api/announcement-search',params=query).status_code==200
    assert calls==[('600519','2026-06-30','2026-09-17','all',2)]
    for overrides in [{'begin':'2026-10-01'},{'begin':'2026-02-30'},{'page':0},{'category':'unknown'}]:
        assert client.get('/api/announcement-search',params={**query,**overrides}).status_code==422
    assert len(calls)==1
