"""Desk 只读证据入口：不触发抓取、AI 或重新回归。"""
import unittest
from unittest.mock import Mock, patch

from routes.newma_desk import FundSymbolRequest, fund_risk_evidence


class RiskEvidenceTests(unittest.TestCase):
    def test_bare_code_resolves_uniquely_and_only_reads_cached_duration(self):
        repo = Mock()
        repo.get_fund_by_identifier.side_effect = lambda code: {'wind_code': code, 'name': '测试债基'} if code == '000001.OF' else None
        with patch('repositories.get_fund_repo', return_value=repo), patch('services.fund_bond_duration_service.FundBondDurationService') as duration:
            duration.return_value.get.return_value = {'status': 'ok', 'as_of_date': '2026-09-10', 'estimated_duration': 3.2, 'r_squared': .8, 'formal_duration_ready': True}
            result = fund_risk_evidence(FundSymbolRequest(symbol='000001'))
            self.assertEqual(result['symbol'], '000001.OF')
            self.assertEqual(result['duration']['estimated_duration'], 3.2)
            self.assertNotIn('formal_duration_ready', result['duration'])
            duration.return_value.get.assert_called_once_with('000001.OF')
            duration.return_value.calculate.assert_not_called()

    def test_ambiguous_identifier_does_not_pick_a_fund(self):
        repo = Mock()
        repo.get_fund_by_identifier.side_effect = lambda code: {'wind_code': code} if code in {'000001.OF', '000001.SH'} else None
        with patch('repositories.get_fund_repo', return_value=repo), patch('services.fund_bond_duration_service.FundBondDurationService') as duration:
            self.assertEqual(fund_risk_evidence(FundSymbolRequest(symbol='000001'))['status'], 'ambiguous')
            duration.assert_not_called()

    def test_unknown_code_does_not_trigger_data_acquisition(self):
        repo = Mock()
        repo.get_fund_by_identifier.return_value = None
        with patch('repositories.get_fund_repo', return_value=repo), patch('services.fund_bond_duration_service.FundBondDurationService') as duration:
            self.assertEqual(fund_risk_evidence(FundSymbolRequest(symbol='000001'))['status'], 'not_found')
            duration.assert_not_called()


if __name__ == '__main__':
    unittest.main()
