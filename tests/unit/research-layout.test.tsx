// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Layout } from '@/components/layout/Layout';

vi.mock('@/hooks/useDarkMode', () => ({ useDarkMode: () => ({dark:false,toggle:vi.fn()}) }));
let mobile = true;
let mediaChanged: ((event: {matches: boolean}) => void) | undefined;
function resize(matches: boolean) { act(() => { mobile = matches; mediaChanged?.({matches}); }); }
const addedPages = [
  ['/macro-monitor', '宏观观察'], ['/catalyst-calendar', '催化剂日历'],
  ['/idea-funnel', '研究机会池'], ['/etf-research', 'ETF 研究'],
  ['/earnings-workbench', '财报研究'], ['/peer-comparison', '同业比较'],
  ['/valuation-workbench', '预测与估值'], ['/thesis-tracker', '投资逻辑'],
  ['/research-memo', '研究备忘录'],
];
function mount(initialPath = '/stock-data', basename = '/') {
  return render(<MemoryRouter basename={basename} initialEntries={[initialPath]}><Routes>
    <Route element={<Layout />}>
      <Route path="stock-data" element={<input aria-label="研究输入" defaultValue="" />} />
      <Route path="watchlist" element={<h1>自选股页面</h1>} />
      {addedPages.map(([path, label]) => <Route key={path} path={path} element={<h1>{label}页面</h1>} />)}
      <Route path="sectors/:key" element={<h1>行业详情页面</h1>} />
    </Route>
  </Routes></MemoryRouter>);
}
beforeEach(() => {
  mobile = true;
  const storage = new Map<string,string>();
  vi.stubGlobal('localStorage',{getItem:(key:string)=>storage.get(key)??null,setItem:(key:string,value:string)=>storage.set(key,value)});
  vi.stubGlobal('matchMedia', vi.fn(() => ({ matches:mobile,
    addEventListener: (_:string,fn:typeof mediaChanged) => { mediaChanged=fn; },
    removeEventListener: () => { mediaChanged=undefined; },
  })));
  // jsdom不实现原生模态行为；这里只测应用状态，焦点/遮罩在现有Chrome验收。
  HTMLDialogElement.prototype.showModal = function() { this.open=true; };
  HTMLDialogElement.prototype.close = function() { this.open=false; this.dispatchEvent(new Event('close')); };
});
afterEach(() => {cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();});

describe('Research独立页响应式导航', () => {
  it('缺失的研究入口均可导航，选中状态及移动标题同步', async () => {
    mount();
    for (const [path, label] of addedPages) {
      fireEvent.click(screen.getByRole('button', {name:'打开导航'}));
      const link = screen.getByRole('link', {name:label});
      expect(link.getAttribute('href')).toBe(path);
      fireEvent.click(link);
      expect(await screen.findByRole('heading', {name:`${label}页面`})).toBeTruthy();
      expect(screen.queryByRole('dialog')).toBeNull();
      expect(screen.getByRole('banner').textContent).toBe(label);
      fireEvent.click(screen.getByRole('button', {name:'打开导航'}));
      expect(screen.getByRole('link', {name:label}).getAttribute('aria-current')).toBe('page');
      fireEvent.click(screen.getByRole('button', {name:'关闭导航'}));
    }
  });

  it('部署在子路径时保留前缀，行业详情不误标总览为当前页', () => {
    mobile = false;
    mount('/mod-runtime/research/sectors/hbm', '/mod-runtime/research');
    expect(screen.getByRole('link', {name:'HBM'}).getAttribute('aria-current')).toBe('page');
    expect(screen.getByRole('link', {name:'产业图谱'}).getAttribute('aria-current')).toBeNull();
    expect(screen.getByRole('link', {name:'财报研究'}).getAttribute('href')).toBe('/mod-runtime/research/earnings-workbench');
    fireEvent.click(screen.getByRole('button', {name:'收起'}));
    expect(screen.getByRole('link', {name:'财报研究'}).getAttribute('title')).toBe('财报研究');
  });

  it('小屏默认只显示菜单按钮，打开后选页自动收起', async () => {
    mount();
    expect(screen.queryByRole('navigation')).toBeNull();
    const open = screen.getByRole('button',{name:'打开导航'});
    expect(open.getAttribute('aria-expanded')).toBe('false');
    fireEvent.click(open);
    expect(screen.getByRole('dialog',{name:'研究导航'})).toBeTruthy();
    expect(screen.getByRole('link',{name:'个股数据'}).getAttribute('aria-current')).toBe('page');
    fireEvent.click(screen.getByRole('link',{name:'自选股'}));
    expect(await screen.findByText('自选股页面')).toBeTruthy();
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });

  it('关闭和取消均收起菜单，点击当前页面也能关闭', () => {
    mount(); const open = screen.getByRole('button',{name:'打开导航'});
    fireEvent.click(open); fireEvent.click(screen.getByRole('button',{name:'关闭导航'}));
    expect(screen.queryByRole('dialog')).toBeNull();
    fireEvent.click(open); fireEvent(screen.getByRole('dialog'),new Event('cancel',{cancelable:true}));
    expect(screen.queryByRole('dialog')).toBeNull();
    fireEvent.click(open); fireEvent.click(screen.getByRole('link',{name:'个股数据'}));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('跨断点不丢正文输入，不改桌面折叠偏好，也不重开旧菜单', () => {
    localStorage.setItem('vr-sidebar','collapsed'); mount();
    fireEvent.change(screen.getByRole('textbox'),{target:{value:'300502'}});
    fireEvent.click(screen.getByRole('button',{name:'打开导航'}));
    resize(false);
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.getByRole('button',{name:'展开'})).toBeTruthy();
    expect(localStorage.getItem('vr-sidebar')).toBe('collapsed');
    expect((screen.getByRole('textbox') as HTMLInputElement).value).toBe('300502');
    resize(true);
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(localStorage.getItem('vr-sidebar')).toBe('collapsed');
  });

  it('iframe嵌入不显示重复导航或菜单按钮', () => {
    vi.stubGlobal('parent',{}); mount();
    expect(screen.queryByRole('navigation')).toBeNull();
    expect(screen.queryByRole('button',{name:'打开导航'})).toBeNull();
    expect(screen.getByRole('textbox')).toBeTruthy();
  });
});
