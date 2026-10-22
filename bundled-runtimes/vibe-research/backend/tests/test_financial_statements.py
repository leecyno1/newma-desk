from types import SimpleNamespace

import pytest
import requests

import astock
import equity_research


def test_sina_uses_field_ids_yuan_and_separate_report_publication(monkeypatch):
    def fetch(url, **kwargs):
        assert kwargs['params'] == {'paperCode': 'sz300502', 'source': 'lrb', 'type': '0', 'page': '1', 'num': '1'}
        assert kwargs['timeout'] == 12
        return SimpleNamespace(raise_for_status=lambda: None, url=url, json=lambda: {'result': {
            'status': {'code': 0}, 'data': {'report_list': {'20260630': {
                'rType': '合并期末', 'rCurrency': 'CNY', 'publish_date': '20260825',
                'data': [{'item_field': 'PARENETP', 'item_value': '7529168039.39'},
                         {'item_field': 'NETPROFIT', 'item_value': '7566314696.14'}],
            }}}}})
    monkeypatch.setattr(requests, 'get', fetch)
    result = astock.financial_statement('300502', 'lrb')
    assert result['values']['NETPROFIT'] == '7566314696.14'
    assert result['period'] == '2026-06-30'
    assert result['period_start'] == '2026-01-01'
    assert result['period_start_basis'] == 'calendar_ytd_rule'
    assert result['report_published_at'] == '2026-08-25'


@pytest.mark.parametrize('scope,currency', [('母公司期末', 'CNY'), ('合并期末', 'USD')])
def test_sina_rejects_unmatched_statement_scope(monkeypatch, scope, currency):
    monkeypatch.setattr(requests, 'get', lambda *args, **kwargs: SimpleNamespace(
        raise_for_status=lambda: None, json=lambda: {'result': {'status': {'code': 0}, 'data': {
            'report_list': {'20260630': {'rType': scope, 'rCurrency': currency}},
        }}}))
    with pytest.raises(ValueError, match='人民币合并报表'):
        astock.financial_statement('300502', 'lrb')


def report(statement, *, period='2026-06-30'):
    return {'period': period, 'period_start': '2026-01-01' if statement != 'fzb' else None,
            'report_published_at': '2026-08-25', 'url': 'https://quotes.sina.cn/test',
            'values': {'lrb': {'NETPROFIT': '7566314696.14', 'PARENETP': '7529168039.39'},
                       'llb': {'MANANETR': '1616408524.15'},
                       'fzb': {'TOTASSET': '36646979659.62', 'TOTLIAB': '12180639783.72'}}[statement]}


def snapshot(loader):
    adapter = equity_research.ChinaEquityResearchAdapter(
        valuation_loader=lambda symbol: {}, financial_loader=lambda symbol: {}, percentile_loader=lambda symbol: {})
    return equity_research.EquityResearchService([adapter], enrichers=[
        equity_research.ChinaStatementEvidenceAdapter(loader),
    ]).snapshot('300502')


def test_consolidated_totals_supply_cash_conversion_and_leverage_not_parent_profit():
    result = snapshot(lambda symbol, statement: report(statement))
    metrics = result['comparisonProfile']['metrics']
    assert metrics['cashConversionPct'] == round(1616408524.15 / 7566314696.14 * 100, 4)
    assert metrics['debtRatioPct'] == round(12180639783.72 / 36646979659.62 * 100, 4)
    ledger = {item['id']: item for item in result['evidenceLedger']}
    assert ledger['disclosure.cn_net_income']['unit'] == 'CNY'
    assert ledger['disclosure.cn_net_income']['value'] == 7566314696.14
    assert ledger['disclosure.cn_net_income']['reportPublishedAt'] == '2026-08-25'
    assert ledger['disclosure.cn_net_income']['publishedAt'] is None
    assert ledger['derived.cash_conversion']['publishedAt'] is None
    assert ledger['derived.cash_conversion']['dependsOn'] == ['disclosure.cn_operating_cash_flow', 'disclosure.cn_net_income']
    assert any('当前整理值' in gap for gap in result['gaps'])


def test_different_statement_periods_do_not_form_cash_conversion():
    result = snapshot(lambda symbol, statement: report(statement, period='2026-03-31' if statement == 'llb' else '2026-06-30'))
    assert result['comparisonProfile']['metrics']['cashConversionPct'] is None
    assert result['comparisonProfile']['metrics']['debtRatioPct'] is not None
    assert any('报告期不一致' in gap for gap in result['gaps'])


def test_one_statement_failure_preserves_other_statements_and_reports_failure():
    def load(symbol, statement):
        if statement == 'llb':
            raise requests.Timeout('source timeout')
        return report(statement)
    result = snapshot(load)
    assert result['comparisonProfile']['metrics']['cashConversionPct'] is None
    assert result['comparisonProfile']['metrics']['debtRatioPct'] is not None
    assert 'cn-statement-llb' in result['workflow']['diagnostics']['failedSources']
    assert any('现金流量表暂不可用' in gap for gap in result['gaps'])


def test_derived_publication_date_is_latest_input_version_not_report_end():
    class Adapter:
        def supports(self, symbol):
            return True

        def load(self, symbol):
            return equity_research.ResearchInputs(symbol=symbol, market='US', name=symbol, currency='USD', evidence=[
                equity_research.Evidence(id='disclosure.edgar_operating_cash_flow', dimension='cash_flow',
                    label='CFO', value=12, source='SEC', source_type='filing', field='CFO', unit='USD',
                    as_of='2026-06-30', period_start='2026-01-01', published_at='2026-08-02'),
                equity_research.Evidence(id='disclosure.edgar_net_income', dimension='profitability',
                    label='NI', value=10, source='SEC', source_type='filing', field='NI', unit='USD',
                    as_of='2026-06-30', period_start='2026-01-01', published_at='2026-08-01'),
            ])

    result = equity_research.EquityResearchService([Adapter()]).snapshot('TEST')
    derived = next(item for item in result['evidenceLedger'] if item['id'] == 'derived.cash_conversion')
    assert derived['asOf'] == '2026-06-30'
    assert derived['publishedAt'] == '2026-08-02'
