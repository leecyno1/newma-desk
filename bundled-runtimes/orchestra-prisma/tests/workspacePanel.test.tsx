// @vitest-environment jsdom

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import WorkspacePanel from '@/components/orchestra/WorkspacePanel';

const portfolio = {
  id: 'portfolio-1',
  owner_id: 'local-user',
  name: '成长组合',
  description: '成长股组合',
  base_currency: 'CNY',
  created_at: '2026-07-24T00:00:00Z',
  updated_at: '2026-07-24T00:00:00Z',
};

const detail = {
  portfolio,
  summary: {
    as_of: '2026-07-24',
    currency: 'CNY',
    cash_balance: '998995',
    market_value: '1200',
    net_asset_value: '1000195',
    total_cost: '1005',
    gross_exposure: '1200',
    unrealized_pnl: '195',
    realized_pnl: '0',
    income: '0',
    fees: '5',
    position_count: 1,
  },
  positions: [{
    asset_code: '300570.SZ',
    asset_name: '太辰光',
    asset_class: 'equity' as const,
    currency: 'CNY',
    quantity: '100',
    average_cost: '10.05',
    last_price: '12',
    market_value: '1200',
    cost_value: '1005',
    unrealized_pnl: '195',
    realized_pnl: '0',
  }],
  transactions: [],
  nav_history: [{
    id: 'nav-1',
    portfolio_id: portfolio.id,
    as_of: '2026-07-24',
    cash_balance: '998995',
    market_value: '1200',
    net_asset_value: '1000195',
    unit_count: '1000000',
    unit_nav: '1.000195',
    total_cost: '1005',
    unrealized_pnl: '195',
    realized_pnl: '0',
    note: '收盘估值',
    created_at: '2026-07-24T00:00:00Z',
  }],
};

const renderPanel = (overrides: Record<string, unknown> = {}) => {
  const props = {
    currentUser: { id: 'local-user', name: '本地管理员', role: 'owner' as const, created_at: '2026-07-24T00:00:00Z' },
    users: [{ id: 'local-user', name: '本地管理员', role: 'owner' as const, created_at: '2026-07-24T00:00:00Z' }],
    portfolios: [portfolio],
    selectedPortfolioId: portfolio.id,
    portfolioDetail: detail,
    secrets: [],
    onCreateUser: vi.fn().mockResolvedValue({ user: { id: 'u-1', name: '研究员', role: 'researcher', created_at: '' }, api_token: 'token' }),
    onLogin: vi.fn().mockResolvedValue({}),
    onLogout: vi.fn().mockResolvedValue({}),
    onCreatePortfolio: vi.fn().mockResolvedValue(portfolio),
    onSelectPortfolio: vi.fn().mockResolvedValue({}),
    onCreateTransaction: vi.fn().mockResolvedValue({}),
    onCreateValuation: vi.fn().mockResolvedValue({}),
    onCreateSecret: vi.fn().mockResolvedValue({}),
    onDeleteSecret: vi.fn().mockResolvedValue({}),
    ...overrides,
  };
  render(<WorkspacePanel {...props} />);
  return props;
};

describe('WorkspacePanel', () => {
  it('renders holdings and records a buy transaction', async () => {
    const user = userEvent.setup();
    const props = renderPanel();

    expect(screen.getByText('1,000,195.00')).toBeTruthy();
    expect(screen.getByText('太辰光')).toBeTruthy();
    await user.selectOptions(screen.getByLabelText('交易类型'), 'buy');
    await user.type(screen.getByLabelText('资产代码'), '300570.SZ');
    await user.type(screen.getByLabelText('资产名称'), '太辰光');
    await user.type(screen.getByLabelText('交易数量'), '50');
    await user.type(screen.getByLabelText('交易价格'), '11.5');
    await user.click(screen.getByRole('button', { name: '记入账本' }));

    await waitFor(() => expect(props.onCreateTransaction).toHaveBeenCalledWith(
      portfolio.id,
      expect.objectContaining({
        transaction_type: 'buy',
        asset_code: '300570.SZ',
        quantity: '50',
        price: '11.5',
      }),
    ));
  });

  it('records a valuation mark and opens a token session', async () => {
    const user = userEvent.setup();
    const props = renderPanel();

    await user.selectOptions(screen.getByLabelText('估值资产'), '300570.SZ');
    await user.type(screen.getByLabelText('估值价格'), '12.8');
    await user.type(screen.getByLabelText('基金份额'), '1000000');
    await user.click(screen.getByRole('button', { name: '记录净值' }));
    await waitFor(() => expect(props.onCreateValuation).toHaveBeenCalledWith(
      portfolio.id,
      expect.objectContaining({
        marks: [{ asset_code: '300570.SZ', price: '12.8', source: 'manual' }],
        unit_count: '1000000',
      }),
    ));

    await user.type(screen.getByLabelText('登录用户 ID'), 'user-2');
    await user.type(screen.getByLabelText('登录 API Token'), 'one-time-token');
    await user.click(screen.getByRole('button', { name: '连接账户' }));
    await waitFor(() => expect(props.onLogin).toHaveBeenCalledWith('user-2', 'one-time-token'));
  });

  it('stores a dedicated external agent credential', async () => {
    const user = userEvent.setup();
    const props = renderPanel();

    await user.selectOptions(screen.getByLabelText('密钥服务'), 'agent');
    await user.type(screen.getByLabelText('密钥标签'), '外部 Agent Token');
    await user.type(screen.getByLabelText('密钥内容'), 'agent-secret-value');
    await user.click(screen.getByRole('button', { name: '保存密钥' }));

    await waitFor(() => expect(props.onCreateSecret).toHaveBeenCalledWith({
      provider: 'agent',
      label: '外部 Agent Token',
      value: 'agent-secret-value',
    }));
  });
});
