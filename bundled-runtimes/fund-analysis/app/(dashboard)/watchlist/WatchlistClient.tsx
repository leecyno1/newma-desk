'use client'

import Link from 'next/link'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Bookmark, CircleAlert, FolderPlus, GitCompareArrows, LoaderCircle, Pencil, Plus, Search, Trash2 } from 'lucide-react'
import {
  drawdownMetric,
  formatAsset,
  formatPercent,
  managerName,
  professionalFundScore,
  professionalPeerGroup,
  returnMetric,
  styleLabel,
  type SimpleFund,
} from '@/lib/simple-fund-view'

type Watchlist = {
  id: string
  name: string
  description?: string | null
  is_default?: boolean
  member_count?: number
}

type WatchlistMember = SimpleFund & {
  memberId: string
  reason: string
}

export default function WatchlistClient() {
  const [watchlists, setWatchlists] = useState<Watchlist[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [members, setMembers] = useState<WatchlistMember[]>([])
  const [keyword, setKeyword] = useState('')
  const [selectedCodes, setSelectedCodes] = useState<string[]>([])
  const [newGroupName, setNewGroupName] = useState('')
  const [creating, setCreating] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const loadWatchlists = useCallback(async (preferredId = '') => {
    const response = await fetch('/api/watchlists', { cache: 'no-store' })
    const payload = await response.json()
    if (!response.ok) throw new Error(payload.error || '加载自选分组失败')
    const next = Array.isArray(payload.watchlists) ? payload.watchlists : []
    setWatchlists(next)
    const nextId = preferredId || selectedId || String(next[0]?.id || '')
    setSelectedId(nextId)
    return nextId
  }, [selectedId])

  const loadMembers = useCallback(async (id: string) => {
    if (!id) {
      setMembers([])
      setLoading(false)
      return
    }
    setLoading(true)
    setError('')
    try {
      const response = await fetch(`/api/watchlists/${encodeURIComponent(id)}/members`, { cache: 'no-store' })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.error || '加载自选基金失败')
      setMembers(payload.members || [])
      setSelectedCodes([])
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : '加载自选基金失败')
      setMembers([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void (async () => {
      try {
        const id = await loadWatchlists()
        await loadMembers(id)
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : '加载自选失败')
        setLoading(false)
      }
    })()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const visibleMembers = useMemo(() => {
    const normalized = keyword.trim().toLowerCase()
    if (!normalized) return members
    return members.filter((member) => `${member.name} ${member.windCode} ${professionalPeerGroup(member)} ${styleLabel(member)}`.toLowerCase().includes(normalized))
  }, [keyword, members])

  const compareHref = `/compare?${new URLSearchParams({ codes: selectedCodes.join(',') }).toString()}`

  async function createGroup() {
    const name = newGroupName.trim()
    if (!name) return
    setCreating(true)
    setError('')
    try {
      const response = await fetch('/api/watchlists', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.error || '创建分组失败')
      setNewGroupName('')
      const id = await loadWatchlists(String(payload.id || ''))
      await loadMembers(id)
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : '创建分组失败')
    } finally {
      setCreating(false)
    }
  }

  async function updateReason(member: WatchlistMember) {
    const nextReason = window.prompt('修改收藏理由', member.reason || '')
    if (nextReason == null) return
    const response = await fetch(`/api/watchlists/members/${encodeURIComponent(member.memberId)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason: nextReason }),
    })
    const payload = await response.json()
    if (!response.ok) {
      setError(payload.error || '更新备注失败')
      return
    }
    setMembers((current) => current.map((item) => item.memberId === member.memberId ? { ...item, reason: nextReason.trim() } : item))
  }

  async function removeMember(member: WatchlistMember) {
    if (!window.confirm(`将“${member.name || member.windCode}”移出当前自选分组？`)) return
    const response = await fetch(`/api/watchlists/members/${encodeURIComponent(member.memberId)}`, { method: 'DELETE' })
    const payload = await response.json()
    if (!response.ok) {
      setError(payload.error || '移出自选失败')
      return
    }
    setMembers((current) => current.filter((item) => item.memberId !== member.memberId))
    setSelectedCodes((current) => current.filter((code) => code !== member.windCode))
    void loadWatchlists(selectedId)
  }

  function toggleCompare(member: WatchlistMember) {
    setError('')
    if (selectedCodes.includes(member.windCode)) {
      setSelectedCodes((current) => current.filter((code) => code !== member.windCode))
      return
    }
    const selectedFunds = members.filter((item) => selectedCodes.includes(item.windCode))
    const targetGroup = professionalPeerGroup(member)
    const lockedGroup = selectedFunds.length ? professionalPeerGroup(selectedFunds[0]) : ''
    if (!targetGroup || (lockedGroup && targetGroup !== lockedGroup)) {
      setError(lockedGroup ? `比较已锁定“${lockedGroup}”，只能选择同类基金。` : '这只基金尚未完成专业分类，暂不能加入比较。')
      return
    }
    if (selectedCodes.length >= 6) return
    setSelectedCodes((current) => [...current, member.windCode])
  }

  return (
    <div className="space-y-7">
      <section className="grid gap-5 lg:grid-cols-[17rem_minmax(0,1fr)]">
        <aside className="h-fit border border-[#dbe1dc] bg-white p-4">
          <div className="flex items-center justify-between"><h2 className="font-bold">自选分组</h2><FolderPlus className="h-4 w-4 text-[#28745c]" /></div>
          <div className="mt-4 space-y-2">
            {watchlists.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => { setSelectedId(String(item.id)); void loadMembers(String(item.id)) }}
                className={`flex w-full items-center justify-between border px-3 py-3 text-left text-sm transition ${selectedId === String(item.id) ? 'border-[#2d775e] bg-[#eaf2ed] text-[#1f5d49]' : 'border-transparent bg-[#f5f7f5] text-[#59665f] hover:border-[#cbd5ce]'}`}
              >
                <span className="truncate font-semibold">{item.name}</span>
                <span className="ml-3 text-xs">{item.member_count || 0}</span>
              </button>
            ))}
          </div>
          <form className="mt-5 border-t border-[#e3e7e3] pt-4" onSubmit={(event) => { event.preventDefault(); void createGroup() }}>
            <label className="text-xs font-bold text-[#64716a]" htmlFor="watchlist-name">新建分组</label>
            <div className="mt-2 flex gap-2">
              <input id="watchlist-name" value={newGroupName} onChange={(event) => setNewGroupName(event.target.value)} placeholder="如：稳健底仓" className="min-w-0 flex-1 border border-[#cfd6d0] px-3 py-2 text-sm outline-none focus:border-[#28745c]" />
              <button type="submit" disabled={creating || !newGroupName.trim()} className="grid h-10 w-10 place-items-center bg-[#173f35] text-white disabled:opacity-40" aria-label="创建分组"><Plus className="h-4 w-4" /></button>
            </div>
          </form>
        </aside>

        <div className="min-w-0 space-y-4">
          <div className="flex flex-col gap-3 border-b border-[#dce1dc] pb-4 sm:flex-row sm:items-center sm:justify-between">
            <label className="relative block max-w-md flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#7a8580]" />
              <input value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="搜索当前分组" className="h-11 w-full border border-[#cfd6d0] bg-white pl-10 pr-3 text-sm outline-none focus:border-[#28745c]" />
            </label>
            <div className="flex gap-2">
              <Link href="/discover" className="inline-flex h-11 items-center gap-2 border border-[#bfc9c2] bg-white px-4 text-sm font-bold text-[#315d4c]"><Plus className="h-4 w-4" />继续找基金</Link>
              {selectedCodes.length >= 2 ? <Link href={compareHref} className="inline-flex h-11 items-center gap-2 bg-[#173f35] px-4 text-sm font-bold text-white"><GitCompareArrows className="h-4 w-4" />比较 {selectedCodes.length} 只</Link> : null}
            </div>
          </div>

          {error ? <div className="flex gap-3 border border-[#e4c78e] bg-[#fff8e8] px-4 py-3 text-sm text-[#78571f]"><CircleAlert className="mt-0.5 h-4 w-4 shrink-0" />{error}</div> : null}

          {loading ? (
            <div className="grid min-h-64 place-items-center border border-[#dbe1dc] bg-white text-sm text-[#66736c]"><span className="flex items-center gap-2"><LoaderCircle className="h-4 w-4 animate-spin" />正在加载自选基金</span></div>
          ) : visibleMembers.length === 0 ? (
            <div className="border border-dashed border-[#cbd3cd] bg-white px-6 py-16 text-center">
              <Bookmark className="mx-auto h-7 w-7 text-[#7c9388]" />
              <h2 className="mt-4 text-lg font-bold">这个分组还没有基金</h2>
              <p className="mt-2 text-sm text-[#6f7b75]">从“找基金”页面加入，或者换一个分组查看。</p>
              <Link href="/discover" className="mt-6 inline-flex h-11 items-center gap-2 bg-[#173f35] px-5 text-sm font-bold text-white"><Plus className="h-4 w-4" />去找基金</Link>
            </div>
          ) : (
            <div className="overflow-x-auto border border-[#dbe1dc] bg-white">
              <table className="w-full min-w-[980px] border-collapse text-left text-sm">
                <thead className="bg-[#f1f4f1] text-xs text-[#66726c]"><tr><th className="w-12 px-4 py-3">对比</th><th className="px-4 py-3">基金</th><th className="px-4 py-3">分类 / 风格</th><th className="px-4 py-3 text-right">近 1 年</th><th className="px-4 py-3 text-right">最大回撤</th><th className="px-4 py-3 text-right">专业评分</th><th className="px-4 py-3 text-right">规模</th><th className="px-4 py-3">收藏理由</th><th className="px-4 py-3 text-right">操作</th></tr></thead>
                <tbody className="divide-y divide-[#e5e9e5]">
                  {visibleMembers.map((member) => {
                    const selected = selectedCodes.includes(member.windCode)
                    const score = professionalFundScore(member)
                    return <tr key={member.memberId} className="align-top transition hover:bg-[#f8faf8]">
                      <td className="px-4 py-4"><button type="button" onClick={() => toggleCompare(member)} className={`grid h-7 w-7 place-items-center border ${selected ? 'border-[#2c765d] bg-[#2c765d] text-white' : 'border-[#c7d0ca] text-transparent hover:border-[#2c765d]'}`} aria-label={selected ? `移出比较：${member.name}` : `加入比较：${member.name}`}>✓</button></td>
                      <td className="px-4 py-4"><Link href={`/funds/${encodeURIComponent(member.windCode)}`} className="font-bold text-[#1b2923] hover:text-[#28745c]">{member.name || member.windCode}</Link><div className="mt-1 text-xs text-[#7b8680]">{member.windCode} · {managerName(member)}</div></td>
                      <td className="px-4 py-4"><div className="max-w-[14rem] font-medium">{professionalPeerGroup(member) || '专业分类待确认'}</div><span className="mt-2 inline-flex bg-[#edf1ed] px-2 py-1 text-xs text-[#5f6b65]">{styleLabel(member)}</span></td>
                      <td className={`px-4 py-4 text-right font-bold ${(returnMetric(member) || 0) < 0 ? 'text-[#a84d47]' : 'text-[#267257]'}`}>{formatPercent(returnMetric(member))}</td>
                      <td className="px-4 py-4 text-right text-[#8b4f48]">{formatPercent(drawdownMetric(member))}</td>
                      <td className="px-4 py-4 text-right font-bold text-[#245f4b]">{score == null ? '—' : score.toFixed(1)}</td>
                      <td className="px-4 py-4 text-right">{formatAsset(member.totalAsset)}</td>
                      <td className="max-w-[17rem] px-4 py-4"><p className="line-clamp-3 text-[#536059]">{member.reason || '暂未填写，可记录为什么关注这只基金。'}</p></td>
                      <td className="px-4 py-4"><div className="flex justify-end gap-2"><button type="button" onClick={() => void updateReason(member)} className="grid h-8 w-8 place-items-center border border-[#ced6d0] text-[#526159] hover:border-[#28745c]" aria-label="修改收藏理由"><Pencil className="h-3.5 w-3.5" /></button><button type="button" onClick={() => void removeMember(member)} className="grid h-8 w-8 place-items-center border border-[#e0ccc8] text-[#9a4d45] hover:border-[#a95249]" aria-label="移出自选"><Trash2 className="h-3.5 w-3.5" /></button></div></td>
                    </tr>
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>
    </div>
  )
}
