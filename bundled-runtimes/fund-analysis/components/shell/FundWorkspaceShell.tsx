'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import {
  Bot,
  ChevronRight,
  Database,
  Menu,
  PanelLeftClose,
  Search,
  X,
} from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import {
  currentFundWorkspaceItem,
  fundWorkspaceDataNavigation,
  fundWorkspaceNavigation,
  isFundWorkspaceItemActive,
  type FundWorkspaceNavigationItem,
} from './fund-workspace-navigation'
import styles from './FundWorkspaceShell.module.css'

function NavigationLink({
  item,
  pathname,
  closePanel,
}: {
  item: FundWorkspaceNavigationItem
  pathname: string
  closePanel: () => void
}) {
  const Icon = item.icon
  const active = isFundWorkspaceItemActive(pathname, item)

  return (
    <Link
      href={item.href}
      className={styles.moduleLink}
      data-active={active || undefined}
      aria-current={active ? 'page' : undefined}
      onClick={closePanel}
    >
      <Icon size={14} aria-hidden="true" />
      <span>{item.label}</span>
      <ChevronRight size={12} aria-hidden="true" />
    </Link>
  )
}

export default function FundWorkspaceShell({ children }: { children: ReactNode }) {
  const pathname = usePathname()
  const [panelOpen, setPanelOpen] = useState(false)
  const [navigationCollapsed, setNavigationCollapsed] = useState(false)
  const [copilotOpen, setCopilotOpen] = useState(false)
  const searchInputRef = useRef<HTMLInputElement>(null)
  const currentItem = currentFundWorkspaceItem(pathname)
  const closePanel = () => setPanelOpen(false)

  useEffect(() => {
    const focusSearch = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() !== 'k' || (!event.metaKey && !event.ctrlKey)) return
      event.preventDefault()
      searchInputRef.current?.focus()
    }
    window.addEventListener('keydown', focusSearch)
    return () => window.removeEventListener('keydown', focusSearch)
  }, [])

  return (
    <div
      className={styles.shell}
      data-panel-open={panelOpen || undefined}
      data-navigation-collapsed={navigationCollapsed || undefined}
    >
      <aside className={styles.sidebar} aria-label="基金研究工作区导航">
        <div className={styles.projectRail}>
          <Link href="/" className={styles.deskMark} aria-label="选基助手首页">
            <span>基</span>
          </Link>

          <div className={styles.railProjects}>
            <button
              type="button"
              className={styles.railProject}
              aria-current="page"
              aria-label="基金研究项目"
              title="基金研究"
              onClick={() => {
                setNavigationCollapsed(false)
                setPanelOpen((value) => !value)
              }}
            >
              <span>基研</span>
            </button>
          </div>

          <div className={styles.railTools}>
            <Link href="/evidence-coverage" aria-label="数据与方法" title="数据与方法">
              <Database size={16} aria-hidden="true" />
            </Link>
          </div>
        </div>

        <div className={styles.projectPanel}>
          <div className={styles.panelHeader}>
            <div>
              <span>FUND RESEARCH</span>
              <strong>基金研究</strong>
              <small>浏览 · 评价 · 归因</small>
            </div>
            <button
              type="button"
              onClick={() => {
                setNavigationCollapsed(true)
                setPanelOpen(false)
              }}
              aria-label="收起菜单"
            >
              <PanelLeftClose size={15} aria-hidden="true" />
            </button>
          </div>

          <p className={styles.panelDescription}>
            从基金数据到经理纪要，用统一证据完成比较、评价和候选。
          </p>

          <nav className={styles.moduleNavigation} aria-label="基金研究模块">
            {fundWorkspaceNavigation.map((group) => (
              <section key={group.label} className={styles.navigationGroup}>
                <h2>{group.label}</h2>
                <div>
                  {group.items.map((item) => (
                    <NavigationLink
                      key={item.href}
                      item={item}
                      pathname={pathname}
                      closePanel={closePanel}
                    />
                  ))}
                </div>
              </section>
            ))}
          </nav>

          <div className={styles.panelFooter}>
            <NavigationLink
              item={fundWorkspaceDataNavigation}
              pathname={pathname}
              closePanel={closePanel}
            />
            <small>独立应用 · Desk Adapter Ready</small>
          </div>
        </div>
      </aside>

      {panelOpen ? (
        <button
          type="button"
          className={styles.mobileScrim}
          aria-label="关闭导航"
          onClick={closePanel}
        />
      ) : null}

      <div className={styles.workspace}>
        <header className={styles.toolbar}>
          <div className={styles.toolbarTitle}>
            <button
              type="button"
              className={styles.menuButton}
              onClick={() => {
                setNavigationCollapsed(false)
                setPanelOpen((value) => !value)
              }}
              aria-label="打开项目菜单"
              aria-expanded={panelOpen}
            >
              <Menu size={16} aria-hidden="true" />
            </button>
            <strong>{currentItem?.label ?? '基金研究'}</strong>
            <span>基金研究</span>
          </div>

          <form className={styles.searchForm} action="/discover" method="get" role="search">
            <Search size={14} aria-hidden="true" />
            <input
              ref={searchInputRef}
              type="search"
              name="search"
              placeholder="搜索基金代码、名称或经理"
              aria-label="搜索基金"
            />
            <kbd>⌘ K</kbd>
          </form>

          <div className={styles.toolbarActions}>
            <Link href="/compare">基金比较</Link>
            <button
              type="button"
              className={styles.copilotButton}
              aria-pressed={copilotOpen}
              onClick={() => setCopilotOpen((value) => !value)}
            >
              <Bot size={15} aria-hidden="true" />
              <span>研究助手</span>
            </button>
          </div>
        </header>

        <div className={styles.contentRow} data-copilot-open={copilotOpen || undefined}>
          <main className={styles.content}>{children}</main>

          {copilotOpen ? (
            <aside className={styles.copilot} aria-label="当前研究助手">
              <div className={styles.copilotHeader}>
                <div>
                  <span>COPILOT</span>
                  <strong>当前研究助手</strong>
                </div>
                <button type="button" onClick={() => setCopilotOpen(false)} aria-label="关闭研究助手">
                  <X size={15} aria-hidden="true" />
                </button>
              </div>
              <div className={styles.copilotBody}>
                <Bot size={22} aria-hidden="true" />
                <strong>基于当前基金证据进行分析</strong>
                <p>调用基金数据、经理纪要和业绩归因，分析记录会单独留存。</p>
                <Link href="/analysis" onClick={() => setCopilotOpen(false)}>
                  进入 AI 分析
                  <ChevronRight size={14} aria-hidden="true" />
                </Link>
              </div>
            </aside>
          ) : null}
        </div>
      </div>
    </div>
  )
}
