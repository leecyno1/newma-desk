import React, { useState } from 'react';
import {
  ArrowDownUp,
  BriefcaseBusiness,
  Copy,
  KeyRound,
  LineChart,
  LogIn,
  LogOut,
  Plus,
  Trash2,
  UserPlus,
  UserRound,
  WalletCards,
} from 'lucide-react';
import type {
  CreatePortfolioTransactionPayload,
  CreatePortfolioValuationPayload,
  CreateUserResponse,
  Portfolio,
  PortfolioAssetClass,
  PortfolioDetail,
  PortfolioTransactionType,
  SecretMetadata,
  UserProfile,
} from '@/types/orchestra';

const today = () => new Date().toISOString().slice(0, 10);
const transactionLabels: Record<PortfolioTransactionType, string> = {
  buy: '买入',
  sell: '卖出',
  cash_in: '资金转入',
  cash_out: '资金转出',
  dividend: '分红',
  interest: '利息',
  fee: '费用',
};

const formatNumber = (value: string | number, digits = 2) => new Intl.NumberFormat('zh-CN', {
  minimumFractionDigits: digits,
  maximumFractionDigits: digits,
}).format(Number(value));

const WorkspacePanel = ({
  currentUser,
  users,
  portfolios,
  selectedPortfolioId,
  portfolioDetail,
  secrets,
  onCreateUser,
  onLogin,
  onLogout,
  onCreatePortfolio,
  onSelectPortfolio,
  onCreateTransaction,
  onCreateValuation,
  onCreateSecret,
  onDeleteSecret,
}: {
  currentUser: UserProfile | null;
  users: UserProfile[];
  portfolios: Portfolio[];
  selectedPortfolioId: string;
  portfolioDetail: PortfolioDetail | null;
  secrets: SecretMetadata[];
  onCreateUser: (name: string, role: UserProfile['role']) => Promise<CreateUserResponse>;
  onLogin: (userId: string, apiToken: string) => Promise<unknown>;
  onLogout: () => Promise<unknown>;
  onCreatePortfolio: (payload: { name: string; description: string; base_currency: string }) => Promise<Portfolio>;
  onSelectPortfolio: (portfolioId: string) => Promise<unknown>;
  onCreateTransaction: (portfolioId: string, payload: CreatePortfolioTransactionPayload) => Promise<unknown>;
  onCreateValuation: (portfolioId: string, payload: CreatePortfolioValuationPayload) => Promise<unknown>;
  onCreateSecret: (payload: { provider: SecretMetadata['provider']; label: string; value: string }) => Promise<unknown>;
  onDeleteSecret: (secretId: string) => Promise<unknown>;
}) => {
  const [submitting, setSubmitting] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const [loginUserId, setLoginUserId] = useState('');
  const [loginToken, setLoginToken] = useState('');
  const [userName, setUserName] = useState('');
  const [userRole, setUserRole] = useState<UserProfile['role']>('researcher');
  const [issuedUser, setIssuedUser] = useState<CreateUserResponse | null>(null);
  const [portfolioName, setPortfolioName] = useState('');
  const [portfolioDescription, setPortfolioDescription] = useState('');
  const [transactionType, setTransactionType] = useState<PortfolioTransactionType>('cash_in');
  const [transactionDate, setTransactionDate] = useState(today());
  const [assetCode, setAssetCode] = useState('');
  const [assetName, setAssetName] = useState('');
  const [assetClass, setAssetClass] = useState<PortfolioAssetClass>('equity');
  const [quantity, setQuantity] = useState('');
  const [price, setPrice] = useState('');
  const [amount, setAmount] = useState('');
  const [fees, setFees] = useState('0');
  const [transactionNotes, setTransactionNotes] = useState('');
  const [valuationDate, setValuationDate] = useState(today());
  const [valuationCode, setValuationCode] = useState('');
  const [valuationPrice, setValuationPrice] = useState('');
  const [unitCount, setUnitCount] = useState('');
  const [valuationNote, setValuationNote] = useState('');
  const [secretProvider, setSecretProvider] = useState<SecretMetadata['provider']>('openai');
  const [secretLabel, setSecretLabel] = useState('');
  const [secretValue, setSecretValue] = useState('');
  const isTrade = transactionType === 'buy' || transactionType === 'sell';

  const execute = async (action: () => Promise<unknown>) => {
    setSubmitting(true);
    setLocalError(null);
    try {
      return await action();
    } catch (reason) {
      setLocalError(reason instanceof Error ? reason.message : '操作失败');
      return null;
    } finally {
      setSubmitting(false);
    }
  };

  const submitLogin = async () => {
    if (!loginUserId.trim() || !loginToken.trim()) return;
    const result = await execute(() => onLogin(loginUserId.trim(), loginToken));
    if (result !== null) {
      setLoginUserId('');
      setLoginToken('');
    }
  };

  const submitUser = async () => {
    if (!userName.trim()) return;
    const result = await execute(() => onCreateUser(userName.trim(), userRole));
    if (result) {
      setIssuedUser(result as CreateUserResponse);
      setUserName('');
    }
  };

  const submitPortfolio = async () => {
    if (!portfolioName.trim()) return;
    const result = await execute(() => onCreatePortfolio({
      name: portfolioName.trim(),
      description: portfolioDescription.trim(),
      base_currency: 'CNY',
    }));
    if (result) {
      const portfolio = result as Portfolio;
      setPortfolioName('');
      setPortfolioDescription('');
      await onSelectPortfolio(portfolio.id);
    }
  };

  const submitTransaction = async () => {
    if (!selectedPortfolioId) return;
    const payload: CreatePortfolioTransactionPayload = {
      trade_date: transactionDate,
      transaction_type: transactionType,
      asset_code: isTrade ? assetCode.trim() : undefined,
      asset_name: isTrade ? assetName.trim() : undefined,
      asset_class: isTrade ? assetClass : 'cash',
      quantity: isTrade ? quantity : '0',
      price: isTrade ? price : '0',
      amount: isTrade ? '0' : amount,
      fees: isTrade ? fees || '0' : '0',
      currency: portfolioDetail?.portfolio.base_currency || 'CNY',
      notes: transactionNotes.trim(),
    };
    const result = await execute(() => onCreateTransaction(selectedPortfolioId, payload));
    if (result !== null) {
      setQuantity('');
      setPrice('');
      setAmount('');
      setTransactionNotes('');
    }
  };

  const submitValuation = async () => {
    if (!selectedPortfolioId) return;
    const marks = valuationCode && valuationPrice
      ? [{ asset_code: valuationCode, price: valuationPrice, source: 'manual' }]
      : [];
    const result = await execute(() => onCreateValuation(selectedPortfolioId, {
      as_of: valuationDate,
      marks,
      unit_count: unitCount || null,
      note: valuationNote.trim(),
    }));
    if (result !== null) {
      setValuationPrice('');
      setValuationNote('');
    }
  };

  const submitSecret = async () => {
    if (!secretLabel.trim() || !secretValue.trim()) return;
    const result = await execute(() => onCreateSecret({
      provider: secretProvider,
      label: secretLabel.trim(),
      value: secretValue,
    }));
    if (result !== null) {
      setSecretLabel('');
      setSecretValue('');
    }
  };

  return (
    <div className="orchestra-console-body orchestra-workspace-body">
      {localError ? <button type="button" className="orchestra-inline-alert" onClick={() => setLocalError(null)}>{localError}</button> : null}

      <section className="orchestra-console-section">
        <div className="orchestra-section-heading"><h3>当前用户</h3><span>{currentUser?.role || '—'}</span></div>
        <div className="orchestra-user-identity">
          <UserRound size={18} />
          <span><strong>{currentUser?.name || '—'}</strong><small>{currentUser?.id || '—'}</small></span>
          {currentUser?.id !== 'local-user' ? (
            <button type="button" onClick={() => void execute(onLogout)} aria-label="退出当前会话" title="退出当前会话"><LogOut size={14} /></button>
          ) : null}
        </div>
        <div className="orchestra-inline-form orchestra-session-form">
          <input value={loginUserId} onChange={(event) => setLoginUserId(event.target.value)} placeholder="用户 ID" aria-label="登录用户 ID" />
          <input type="password" value={loginToken} onChange={(event) => setLoginToken(event.target.value)} placeholder="API Token" aria-label="登录 API Token" autoComplete="off" />
          <button type="button" onClick={() => void submitLogin()} disabled={submitting || !loginUserId.trim() || !loginToken.trim()}><LogIn size={14} /> 连接账户</button>
        </div>
      </section>

      {currentUser?.role === 'owner' ? (
        <section className="orchestra-console-section">
          <div className="orchestra-section-heading"><h3>用户与权限</h3><span>{users.length}</span></div>
          <div className="orchestra-user-grid">
            {users.map((user) => <div key={user.id}><span><strong>{user.name}</strong><small>{user.id}</small></span><b>{user.role}</b></div>)}
          </div>
          <div className="orchestra-inline-form orchestra-user-form">
            <input value={userName} onChange={(event) => setUserName(event.target.value)} placeholder="用户名称" aria-label="用户名称" />
            <select value={userRole} onChange={(event) => setUserRole(event.target.value as UserProfile['role'])} aria-label="用户角色">
              <option value="manager">manager</option><option value="researcher">researcher</option><option value="viewer">viewer</option>
            </select>
            <button type="button" onClick={() => void submitUser()} disabled={submitting || !userName.trim()}><UserPlus size={14} /> 新建用户</button>
          </div>
          {issuedUser ? (
            <div className="orchestra-issued-token">
              <span><strong>{issuedUser.user.name}</strong><small>一次性 API Token</small></span>
              <code>{issuedUser.api_token}</code>
              <button type="button" onClick={() => void navigator.clipboard.writeText(issuedUser.api_token)} aria-label="复制一次性 API Token" title="复制"><Copy size={14} /></button>
            </div>
          ) : null}
        </section>
      ) : null}

      <section className="orchestra-console-section">
        <div className="orchestra-section-heading"><h3>基金组合</h3><span>{portfolios.length}</span></div>
        <div className="orchestra-portfolio-switcher">
          {portfolios.map((portfolio) => (
            <button type="button" key={portfolio.id} className={selectedPortfolioId === portfolio.id ? 'is-active' : ''} onClick={() => void onSelectPortfolio(portfolio.id)}>
              <BriefcaseBusiness size={14} /><span><strong>{portfolio.name}</strong><small>{portfolio.base_currency}</small></span><LineChart size={13} />
            </button>
          ))}
        </div>
        <div className="orchestra-inline-form">
          <input value={portfolioName} onChange={(event) => setPortfolioName(event.target.value)} placeholder="组合名称" aria-label="组合名称" />
          <textarea rows={2} value={portfolioDescription} onChange={(event) => setPortfolioDescription(event.target.value)} placeholder="投资目标或风险约束" aria-label="组合说明" />
          <button type="button" onClick={() => void submitPortfolio()} disabled={submitting || !portfolioName.trim()}><Plus size={14} /> 新建组合</button>
        </div>
      </section>

      {portfolioDetail ? (
        <>
          <section className="orchestra-console-section">
            <div className="orchestra-section-heading"><h3>组合总览</h3><span>{portfolioDetail.summary.as_of}</span></div>
            <div className="orchestra-ledger-metrics">
              <div><span>净资产</span><strong>{formatNumber(portfolioDetail.summary.net_asset_value)}</strong></div>
              <div><span>现金</span><strong>{formatNumber(portfolioDetail.summary.cash_balance)}</strong></div>
              <div><span>持仓市值</span><strong>{formatNumber(portfolioDetail.summary.market_value)}</strong></div>
              <div><span>未实现损益</span><strong>{formatNumber(portfolioDetail.summary.unrealized_pnl)}</strong></div>
            </div>
            <div className="orchestra-position-table">
              <div className="is-header"><span>资产</span><span>数量</span><span>成本/现价</span><span>市值</span></div>
              {portfolioDetail.positions.length === 0 ? <p>暂无持仓</p> : portfolioDetail.positions.map((position) => (
                <div key={position.asset_code}>
                  <span><strong>{position.asset_name}</strong><small>{position.asset_code}</small></span>
                  <span>{formatNumber(position.quantity, 4)}</span>
                  <span>{formatNumber(position.average_cost, 4)} / {formatNumber(position.last_price, 4)}</span>
                  <span>{formatNumber(position.market_value)}</span>
                </div>
              ))}
            </div>
          </section>

          <section className="orchestra-console-section orchestra-ledger-entry">
            <div className="orchestra-section-heading"><h3>交易账本</h3><span>{portfolioDetail.transactions.length}</span></div>
            <div className="orchestra-ledger-form">
              <select value={transactionType} onChange={(event) => setTransactionType(event.target.value as PortfolioTransactionType)} aria-label="交易类型">
                {Object.entries(transactionLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
              <input type="date" value={transactionDate} onChange={(event) => setTransactionDate(event.target.value)} aria-label="交易日期" />
              {isTrade ? (
                <>
                  <input value={assetCode} onChange={(event) => setAssetCode(event.target.value)} placeholder="资产代码" aria-label="资产代码" />
                  <input value={assetName} onChange={(event) => setAssetName(event.target.value)} placeholder="资产名称" aria-label="资产名称" />
                  <select value={assetClass} onChange={(event) => setAssetClass(event.target.value as PortfolioAssetClass)} aria-label="资产类别">
                    <option value="equity">股票</option><option value="bond">债券</option><option value="fund">基金</option><option value="commodity">商品</option><option value="future">期货</option><option value="option">期权</option><option value="other">其他</option>
                  </select>
                  <input inputMode="decimal" value={quantity} onChange={(event) => setQuantity(event.target.value)} placeholder="数量" aria-label="交易数量" />
                  <input inputMode="decimal" value={price} onChange={(event) => setPrice(event.target.value)} placeholder="价格" aria-label="交易价格" />
                  <input inputMode="decimal" value={fees} onChange={(event) => setFees(event.target.value)} placeholder="费用" aria-label="交易费用" />
                </>
              ) : (
                <input inputMode="decimal" value={amount} onChange={(event) => setAmount(event.target.value)} placeholder="金额" aria-label="交易金额" />
              )}
              <input value={transactionNotes} onChange={(event) => setTransactionNotes(event.target.value)} placeholder="备注" aria-label="交易备注" />
              <button type="button" onClick={() => void submitTransaction()} disabled={submitting || (isTrade ? !assetCode || !assetName || !quantity || !price : !amount)}><ArrowDownUp size={14} /> 记入账本</button>
            </div>
            <div className="orchestra-transaction-list">
              {portfolioDetail.transactions.slice(0, 8).map((transaction) => (
                <div key={transaction.id}><span><strong>{transactionLabels[transaction.transaction_type]}</strong><small>{transaction.trade_date} · {transaction.asset_name || transaction.notes || '现金'}</small></span><b>{formatNumber(transaction.amount)}</b></div>
              ))}
            </div>
          </section>

          <section className="orchestra-console-section">
            <div className="orchestra-section-heading"><h3>估值与净值</h3><span>{portfolioDetail.nav_history.length}</span></div>
            <div className="orchestra-ledger-form orchestra-valuation-form">
              <input type="date" value={valuationDate} onChange={(event) => setValuationDate(event.target.value)} aria-label="估值日期" />
              <select value={valuationCode} onChange={(event) => setValuationCode(event.target.value)} aria-label="估值资产">
                <option value="">仅记录净值</option>
                {portfolioDetail.positions.map((position) => <option key={position.asset_code} value={position.asset_code}>{position.asset_name} · {position.asset_code}</option>)}
              </select>
              <input inputMode="decimal" value={valuationPrice} onChange={(event) => setValuationPrice(event.target.value)} placeholder="收盘价" aria-label="估值价格" disabled={!valuationCode} />
              <input inputMode="decimal" value={unitCount} onChange={(event) => setUnitCount(event.target.value)} placeholder="基金份额" aria-label="基金份额" />
              <input value={valuationNote} onChange={(event) => setValuationNote(event.target.value)} placeholder="估值备注" aria-label="估值备注" />
              <button type="button" onClick={() => void submitValuation()} disabled={submitting || Boolean(valuationCode && !valuationPrice)}><WalletCards size={14} /> 记录净值</button>
            </div>
            <div className="orchestra-nav-history">
              {portfolioDetail.nav_history.slice(0, 8).map((item) => (
                <div key={item.id}><span><strong>{item.as_of}</strong><small>{item.note || '净值快照'}</small></span><b>{formatNumber(item.net_asset_value)}{item.unit_nav ? ` · ${formatNumber(item.unit_nav, 6)}` : ''}</b></div>
              ))}
            </div>
          </section>
        </>
      ) : null}

      <section className="orchestra-console-section">
        <div className="orchestra-section-heading"><h3>隔离密钥</h3><span>{secrets.length}</span></div>
        <div className="orchestra-workspace-list">
          {secrets.map((secret) => (
            <div key={secret.id}><KeyRound size={14} /><span><strong>{secret.label}</strong><small>{secret.provider} · 当前用户</small></span><button type="button" onClick={() => void execute(() => onDeleteSecret(secret.id))} aria-label={`删除 ${secret.label}`}><Trash2 size={13} /></button></div>
          ))}
        </div>
        <div className="orchestra-inline-form">
          <select value={secretProvider} onChange={(event) => setSecretProvider(event.target.value as SecretMetadata['provider'])} aria-label="密钥服务"><option value="openai">LLM</option><option value="agent">Agent 接入</option><option value="tushare">Tushare</option><option value="tavily">Tavily</option><option value="ima">IMA</option></select>
          <input value={secretLabel} onChange={(event) => setSecretLabel(event.target.value)} placeholder="密钥标签" aria-label="密钥标签" />
          <input type="password" value={secretValue} onChange={(event) => setSecretValue(event.target.value)} placeholder="密钥内容" aria-label="密钥内容" autoComplete="off" />
          <button type="button" onClick={() => void submitSecret()} disabled={submitting || !secretLabel.trim() || !secretValue.trim()}><Plus size={14} /> 保存密钥</button>
        </div>
      </section>
    </div>
  );
};

export default WorkspacePanel;
