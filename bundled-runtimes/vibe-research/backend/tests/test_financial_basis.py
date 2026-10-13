from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient

import app as app_module
import astock


@pytest.mark.parametrize('basis,indicator', [('ytd', '按报告期'), ('quarter', '按单季度'), ('annual', '按年度')])
def test_financial_basis_uses_upstream_dataset_and_preserves_zero(monkeypatch, basis, indicator):
    def fetch(name, **kwargs):
        assert name == 'stock_financial_abstract_ths'
        assert kwargs == {'symbol': '600519', 'indicator': indicator}
        row = {'报告期': '2026-06-30', '基本每股收益': 0, '营业总收入': '123亿元'}
        return SimpleNamespace(empty=False, iloc=[SimpleNamespace(to_dict=lambda: row)])
    monkeypatch.setattr(astock, 'akshare_call', fetch)
    result = astock.financials('600519', basis)
    assert result['basis'] == basis
    assert result['eps'] == 0
    assert result['net_profit'] is None


def test_financial_cache_isolates_basis_and_rejects_ttm(monkeypatch):
    monkeypatch.setattr(app_module, '_FIN_CACHE', {})
    calls = []
    def financials(code, basis='ytd'):
        calls.append((code, basis))
        return {'basis': basis, 'revenue': '123亿元' if basis == 'ytd' else '40亿元'}
    monkeypatch.setattr(astock, 'financials', financials)
    client = TestClient(app_module.app)
    for basis in ['ytd', 'quarter', 'ytd', 'quarter']:
        result = client.get('/api/financials', params={'code': '600519', 'basis': basis})
        assert result.status_code == 200
        assert result.json()['data']['basis'] == basis
    assert len(calls) == 2
    assert client.get('/api/financials?code=600519').json()['data']['basis'] == 'ytd'
    assert client.get('/api/financials?code=600519&basis=ttm').status_code == 422
