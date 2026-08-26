'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  CalendarDays,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleAlert,
  FileSearch,
  FolderOpen,
  LoaderCircle,
  RefreshCw,
  Search,
  Tag,
  X,
} from 'lucide-react'
import ManagerResearchGrid, { type ManagerResearchProfile } from './ManagerResearchGrid'

type ResearchMemo = {
  id: string
  manager_id?: string | null
  manager_name?: string | null
  manager_ids?: string[]
  manager_names?: string[]
  manager_links?: Array<{
    manager_id?: string | null
    manager_name?: string | null
    manager_company?: string | null
    manager_management_years?: number | string | null
  }>
  title: string
  report_date?: string | null
  report_date_source?: string | null
  report_date_precision?: string | null
  source?: string | null
  summary?: string | null
  content?: string | null
  tags?: string[]
  viewpoint_topics?: string[]
  research_domains?: string[]
  classifications?: string[]
  style_labels?: string[]
  fund_ids?: string[]
  key_points?: string[]
  review_status?: string | null
  local_relative_path?: string | null
  local_source_path?: string | null
  source_hash?: string | null
  llm_extraction_status?: string | null
  extraction_provider?: string | null
  extraction_model?: string | null
  llm_extraction_error?: string | null
  review_proposals?: Array<{
    kind?: string
    identity_verification?: {
      status?: string
    }
  }>
}

type ScanCounts = {
  created: number
  updated: number
  unchanged: number
  failed: number
  supported: number
}

type ResearchFolder = {
  id: string
  name: string
  path: string
  status: string
  last_scan_at?: string | null
  last_scan_counts?: ScanCounts | null
}

type PendingReview = {
  id: string
  report_id: string
  report_title: string
  kind: 'manager' | 'fund' | 'classification' | 'style_label' | 'tag'
  value: string
  confidence: number
  candidate_id?: string | null
  extraction_source?: string | null
  scope?: 'manager' | 'fund' | null
  target_fund_ids?: string[]
  source_ref: {
    relative_path: string
    excerpt: string
  }
}

type ReviewFilter = 'manager' | 'labels' | 'all'
type ResearchDomain = '' | 'equity' | 'fixed_income'
type LibraryView = 'managers' | 'memos' | 'reviews'

const emptyCounts: ScanCounts = { created: 0, updated: 0, unchanged: 0, failed: 0, supported: 0 }
const explicitManagerSources = new Set(['explicit_field', 'manager_catalog_title', 'filename_pattern', 'llm'])
const viewpointTopicOrder = ['A股', '港股', '债市', '科技', '医药', '消费', '周期', '新能源', '金融地产', '信用债', '利率债', '久期', '杠杆', '资金利率', '政策', '转债']

function memoManagerNames(memo: ResearchMemo) {
  const names = (memo.manager_names || []).map((name) => name.trim()).filter(Boolean)
  if (names.length) return Array.from(new Set(names))
  const fallback = memo.manager_name?.trim() || memo.manager_id?.trim()
  return fallback ? [fallback] : ['经理待识别']
}

function managerLabel(memo: ResearchMemo) {
  return memoManagerNames(memo).join('、')
}

function managerCompany(memo: ResearchMemo) {
  return Array.from(new Set(
    (memo.manager_links || [])
      .map((link) => String(link.manager_company || '').trim())
      .filter(Boolean),
  )).join('、')
}

function managementYears(memo: ResearchMemo) {
  const values = (memo.manager_links || [])
    .map((link) => Number(link.manager_management_years))
    .filter((value) => Number.isFinite(value) && value >= 0)
  return values.length === 1 ? `${values[0].toFixed(1)} 年` : ''
}

function memoDomainLabel(memo: ResearchMemo) {
  const domains = memo.research_domains || []
  if (domains.includes('equity') && domains.includes('fixed_income')) return '股债多资产观点'
  if (domains.includes('equity')) return '权益观点'
  if (domains.includes('fixed_income')) return '固收观点'
  return '综合观点'
}

function formatDate(value?: string | null, withTime = false) {
  if (!value) return '尚未扫描'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', withTime ? { dateStyle: 'medium', timeStyle: 'short' } : { dateStyle: 'medium' })
}

function memoDateLabel(memo: ResearchMemo) {
  if (!memo.report_date) return '日期待确认'
  const value = String(memo.report_date).slice(0, 10)
  if (memo.report_date_precision === 'quarter') {
    const month = Number(value.slice(5, 7))
    return `${value.slice(0, 4)} Q${Math.floor((month - 1) / 3) + 1}`
  }
  if (memo.report_date_precision === 'month') return `${value.slice(0, 7)} 月`
  return formatDate(value)
}

function memoIdentityLabel(memo: ResearchMemo) {
  const statuses = (memo.review_proposals || [])
    .filter((proposal) => proposal.kind === 'manager')
    .map((proposal) => proposal.identity_verification?.status || '')
  if (statuses.includes('identity_conflict')) return { label: '身份待复核', tone: 'warning' }
  if (statuses.includes('exact_name_evidence_incomplete')) return { label: '身份已关联 · 证据待补', tone: 'warning' }
  if (statuses.includes('unique_exact_name')) return { label: '身份已核验', tone: 'verified' }
  if (memoManagerNames(memo)[0] !== '经理待识别') return { label: '历史已关联', tone: 'neutral' }
  return null
}

function reviewKind(kind: PendingReview['kind']) {
  return ({ manager: '基金经理', fund: '关联基金', classification: '基金分类', style_label: '风格标签', tag: '标签' })[kind]
}

export default function ResearchLibraryClient({ initialQuery = '' }: { initialQuery?: string }) {
  const [memos, setMemos] = useState<ResearchMemo[]>([])
  const [total, setTotal] = useState(0)
  const [folders, setFolders] = useState<ResearchFolder[]>([])
  const [selectedFolderId, setSelectedFolderId] = useState('')
  const [folderPath, setFolderPath] = useState('')
  const [pendingReviews, setPendingReviews] = useState<PendingReview[]>([])
  const [loading, setLoading] = useState(true)
  const [folderLoading, setFolderLoading] = useState(true)
  const [connecting, setConnecting] = useState(false)
  const [scanning, setScanning] = useState(false)
  const [reviewingId, setReviewingId] = useState('')
  const [bulkReviewing, setBulkReviewing] = useState(false)
  const [reviewFilter, setReviewFilter] = useState<ReviewFilter>('manager')
  const [libraryView, setLibraryView] = useState<LibraryView>(initialQuery ? 'memos' : 'managers')
  const [managerQuery, setManagerQuery] = useState('')
  const [error, setError] = useState('')
  const [folderMessage, setFolderMessage] = useState('')
  const [query, setQuery] = useState(initialQuery)
  const [selectedManager, setSelectedManager] = useState('')
  const [selectedDomain, setSelectedDomain] = useState<ResearchDomain>('')
  const [selectedTopic, setSelectedTopic] = useState('')
  const [selectedYear, setSelectedYear] = useState('')
  const [selectedMemo, setSelectedMemo] = useState<ResearchMemo | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [lastScanCounts, setLastScanCounts] = useState<ScanCounts | null>(null)

  const selectedFolder = folders.find((folder) => folder.id === selectedFolderId) || folders[0] || null
  const displayedCounts = lastScanCounts || selectedFolder?.last_scan_counts || emptyCounts
  const reviewCounts = useMemo(() => ({
    manager: pendingReviews.filter((review) => review.kind === 'manager').length,
    labels: pendingReviews.filter((review) => ['classification', 'style_label', 'tag'].includes(review.kind)).length,
    all: pendingReviews.length,
  }), [pendingReviews])
  const visibleReviews = useMemo(() => pendingReviews.filter((review) => {
    if (reviewFilter === 'manager') return review.kind === 'manager'
    if (reviewFilter === 'labels') return ['classification', 'style_label', 'tag'].includes(review.kind)
    return true
  }), [pendingReviews, reviewFilter])
  const safeManagerReviewSummary = useMemo(() => {
    const reports = new Map<string, Set<string>>()
    for (const review of pendingReviews) {
      if (
        review.kind !== 'manager'
        || review.confidence < 0.88
        || !review.candidate_id
        || !explicitManagerSources.has(String(review.extraction_source || ''))
        || !review.source_ref.excerpt?.trim()
      ) continue
      const identities = reports.get(review.report_id) || new Set<string>()
      identities.add(review.candidate_id)
      reports.set(review.report_id, identities)
    }
    return {
      confirmable: reports.size,
      multiManager: Array.from(reports.values()).filter((identities) => identities.size > 1).length,
    }
  }, [pendingReviews])
  const highConfidenceLabelCount = useMemo(
    () => pendingReviews.filter((review) => (
      ['classification', 'style_label', 'tag'].includes(review.kind)
      && review.confidence >= 0.9
      && review.extraction_source !== 'llm'
    )).length,
    [pendingReviews],
  )
  const reviewGroups = useMemo(() => {
    const groups = new Map<string, { reportId: string; title: string; relativePath: string; items: PendingReview[] }>()
    for (const review of visibleReviews) {
      const group = groups.get(review.report_id) || {
        reportId: review.report_id,
        title: review.report_title,
        relativePath: review.source_ref.relative_path,
        items: [],
      }
      group.items.push(review)
      groups.set(review.report_id, group)
    }
    const kindOrder: Record<PendingReview['kind'], number> = { manager: 0, fund: 1, classification: 2, style_label: 3, tag: 4 }
    return Array.from(groups.values()).map((group) => ({
      ...group,
      items: group.items.sort((left, right) => kindOrder[left.kind] - kindOrder[right.kind] || right.confidence - left.confidence),
    }))
  }, [visibleReviews])
  const llmUnavailableCount = useMemo(
    () => memos.filter((memo) => ['failed', 'unavailable'].includes(String(memo.llm_extraction_status || ''))).length,
    [memos],
  )

  const loadMemos = useCallback(async (folderId = '') => {
    setLoading(true)
    setError('')
    try {
      const readPage = async (page: number) => {
        const params = new URLSearchParams({ limit: '50', page: String(page) })
        if (folderId) params.set('folder_id', folderId)
        const response = await fetch(`/api/research-memos?${params.toString()}`, { cache: 'no-store' })
        const payload = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(payload.error || '调研纪要库暂时不可用')
        return payload
      }
      const firstPage = await readPage(1)
      const totalCount = Number(firstPage.total || 0)
      const allMemos = Array.isArray(firstPage.data) ? [...firstPage.data] : []
      const pageCount = Math.ceil(totalCount / 50)
      for (let page = 2; page <= pageCount; page += 1) {
        const payload = await readPage(page)
        if (Array.isArray(payload.data)) allMemos.push(...payload.data)
      }
      setMemos(allMemos)
      setTotal(totalCount)
    } catch (loadError) {
      setMemos([])
      setTotal(0)
      setError(loadError instanceof Error ? loadError.message : '调研纪要库暂时不可用')
    } finally {
      setLoading(false)
    }
  }, [])

  const loadReviews = useCallback(async (folderId = '') => {
    const suffix = folderId ? `?folder_id=${encodeURIComponent(folderId)}` : ''
    const response = await fetch('/api/research-folders/reviews' + suffix, { cache: 'no-store' })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(payload.error || '待确认内容暂时不可用')
    setPendingReviews(Array.isArray(payload.data) ? payload.data : [])
  }, [])

  const loadFolders = useCallback(async (preferredFolderId = '') => {
    setFolderLoading(true)
    try {
      const response = await fetch('/api/research-folders', { cache: 'no-store' })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload.error || '本地文件夹服务暂时不可用')
      const nextFolders = Array.isArray(payload.data) ? payload.data as ResearchFolder[] : []
      setFolders(nextFolders)
      const activeId = preferredFolderId && nextFolders.some((folder) => folder.id === preferredFolderId)
        ? preferredFolderId
        : nextFolders[0]?.id || ''
      setSelectedFolderId(activeId)
      setFolderPath((current) => current || nextFolders[0]?.path || '')
      await loadReviews(activeId)
    } catch (loadError) {
      setFolderMessage(loadError instanceof Error ? loadError.message : '本地文件夹服务暂时不可用')
    } finally {
      setFolderLoading(false)
    }
  }, [loadReviews])

  useEffect(() => {
    const timer = globalThis.setTimeout(() => {
      void loadFolders()
    }, 0)
    return () => globalThis.clearTimeout(timer)
  }, [loadFolders])

  useEffect(() => {
    if (!selectedFolderId) return
    const timer = globalThis.setTimeout(() => {
      void loadMemos(selectedFolderId)
    }, 0)
    return () => globalThis.clearTimeout(timer)
  }, [loadMemos, selectedFolderId])

  const filteredMemos = useMemo(() => {
    const normalized = query.trim().toLowerCase()
    return memos.filter((memo) => {
      if (selectedManager && !memoManagerNames(memo).includes(selectedManager)) return false
      if (selectedDomain && !(memo.research_domains || []).includes(selectedDomain)) return false
      if (selectedTopic && !(memo.viewpoint_topics || []).includes(selectedTopic)) return false
      if (selectedYear && String(memo.report_date || '').slice(0, 4) !== selectedYear) return false
      if (!normalized) return true
      return [
        memo.title,
        memo.summary,
        memo.source,
        memo.local_relative_path,
        managerLabel(memo),
        managerCompany(memo),
        ...(memo.viewpoint_topics || []),
        ...(memo.tags || []),
        ...(memo.classifications || []),
        ...(memo.style_labels || []),
        ...(memo.fund_ids || []),
      ].join(' ').toLowerCase().includes(normalized)
    })
  }, [memos, query, selectedDomain, selectedManager, selectedTopic, selectedYear])

  const managerGroups = useMemo(() => {
    const counts = new Map<string, number>()
    for (const memo of memos) {
      for (const name of memoManagerNames(memo)) counts.set(name, (counts.get(name) || 0) + 1)
    }
    return Array.from(counts, ([name, count]) => ({ name, count }))
      .sort((left, right) => right.count - left.count || left.name.localeCompare(right.name, 'zh-CN'))
  }, [memos])

  const managerProfiles = useMemo(() => {
    const profiles = new Map<string, {
      id: string
      name: string
      company: string
      managementYears: string
      memos: ResearchMemo[]
      fundIds: Set<string>
      topics: Map<string, number>
      labels: Set<string>
    }>()
    for (const memo of memos) {
      for (const name of memoManagerNames(memo)) {
        if (name === '经理待识别') continue
        const managerLink = (memo.manager_links || []).find((link) => link.manager_name === name)
        const profile = profiles.get(name) || {
          id: String(managerLink?.manager_id || ''),
          name,
          company: String(managerLink?.manager_company || ''),
          managementYears: managementYears(memo),
          memos: [],
          fundIds: new Set<string>(),
          topics: new Map<string, number>(),
          labels: new Set<string>(),
        }
        if (!profile.id && managerLink?.manager_id) profile.id = String(managerLink.manager_id)
        if (!profile.company && managerLink?.manager_company) profile.company = String(managerLink.manager_company)
        if (!profile.managementYears) profile.managementYears = managementYears(memo)
        profile.memos.push(memo)
        for (const fundId of memo.fund_ids || []) profile.fundIds.add(fundId)
        for (const topic of memo.viewpoint_topics || []) profile.topics.set(topic, (profile.topics.get(topic) || 0) + 1)
        for (const label of [...(memo.classifications || []), ...(memo.style_labels || []), ...(memo.tags || [])]) profile.labels.add(label)
        profiles.set(name, profile)
      }
    }
    return Array.from(profiles.values()).map((profile) => ({
      ...profile,
      memos: profile.memos.sort((left, right) => String(right.report_date || '').localeCompare(String(left.report_date || ''))),
      latestDate: profile.memos.map((memo) => String(memo.report_date || '')).filter(Boolean).sort().at(-1) || '',
      topTopics: Array.from(profile.topics, ([topic, count]) => ({ topic, count })).sort((left, right) => right.count - left.count).slice(0, 5),
      labels: Array.from(profile.labels).slice(0, 6),
      fundCount: profile.fundIds.size,
    })).sort((left, right) => right.memos.length - left.memos.length || left.name.localeCompare(right.name, 'zh-CN'))
  }, [memos])

  const visibleManagerProfiles = useMemo<ManagerResearchProfile[]>(() => {
    const normalized = managerQuery.trim().toLowerCase()
    return managerProfiles.filter((profile) => !normalized || [
      profile.name,
      profile.company,
      ...profile.topTopics.map((item) => item.topic),
      ...profile.labels,
    ].join(' ').toLowerCase().includes(normalized)).map((profile) => ({
      id: profile.id,
      name: profile.name,
      company: profile.company,
      managementYears: profile.managementYears,
      memoCount: profile.memos.length,
      fundCount: profile.fundCount,
      latestDate: profile.latestDate,
      latestMemoTitle: profile.memos[0]?.title || '',
      topTopics: profile.topTopics,
      labels: profile.labels,
    }))
  }, [managerProfiles, managerQuery])

  const availableYears = useMemo(() => Array.from(new Set(
    memos.map((memo) => String(memo.report_date || '').slice(0, 4)).filter((year) => /^20\d{2}$/.test(year)),
  )).sort().reverse(), [memos])

  const domainCounts = useMemo(() => ({
    equity: memos.filter((memo) => (memo.research_domains || []).includes('equity')).length,
    fixed_income: memos.filter((memo) => (memo.research_domains || []).includes('fixed_income')).length,
  }), [memos])

  const topicBaseMemos = useMemo(() => memos.filter((memo) => {
    if (selectedDomain && !(memo.research_domains || []).includes(selectedDomain)) return false
    if (selectedYear && String(memo.report_date || '').slice(0, 4) !== selectedYear) return false
    return true
  }), [memos, selectedDomain, selectedYear])

  const topicCounts = useMemo(() => {
    const counts = new Map<string, number>()
    for (const memo of topicBaseMemos) {
      for (const topic of memo.viewpoint_topics || []) counts.set(topic, (counts.get(topic) || 0) + 1)
    }
    return viewpointTopicOrder
      .map((topic) => ({ topic, count: counts.get(topic) || 0 }))
      .filter((item) => item.count > 0)
  }, [topicBaseMemos])

  const windVaneTopics = useMemo(
    () => [...topicCounts].sort((left, right) => right.count - left.count || viewpointTopicOrder.indexOf(left.topic) - viewpointTopicOrder.indexOf(right.topic)).slice(0, 5),
    [topicCounts],
  )

  const classifiedManagerCount = useMemo(() => new Set(
    memos.flatMap((memo) => (memo.manager_ids || []).filter(Boolean)),
  ).size, [memos])

  const latestMemoDate = useMemo(() => [...memos]
    .map((memo) => String(memo.report_date || ''))
    .filter(Boolean)
    .sort()
    .at(-1) || '', [memos])

  async function connectFolder() {
    const path = folderPath.trim()
    if (!path) {
      setFolderMessage('请输入本地文件夹路径')
      return
    }
    setConnecting(true)
    setFolderMessage('')
    try {
      const response = await fetch('/api/research-folders', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path }),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload.error || '无法连接本地文件夹')
      const folder = payload.folder as ResearchFolder
      setSelectedFolderId(folder.id)
      setFolderMessage('文件夹已连接，可以扫描更新')
      await loadFolders(folder.id)
    } catch (connectError) {
      setFolderMessage(connectError instanceof Error ? connectError.message : '无法连接本地文件夹')
    } finally {
      setConnecting(false)
    }
  }

  function selectFolder(folderId: string) {
    const folder = folders.find((item) => item.id === folderId)
    if (!folder) return
    setSelectedFolderId(folder.id)
    setFolderPath(folder.path)
    setLastScanCounts(null)
    setFolderMessage('')
    void loadReviews(folder.id).catch((loadError) => {
      setFolderMessage(loadError instanceof Error ? loadError.message : '待确认内容暂时不可用')
    })
  }

  async function scanFolder() {
    if (!selectedFolder) return
    setScanning(true)
    setFolderMessage('')
    try {
      const response = await fetch(`/api/research-folders/${encodeURIComponent(selectedFolder.id)}/scan`, { method: 'POST' })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload.error || '扫描失败')
      setLastScanCounts(payload.counts || emptyCounts)
      const projectedCount = Number(payload.profile_projection?.projected_count || 0)
      const deletedCount = Number(payload.profile_projection?.deleted_count || 0)
      const profileMessage = projectedCount
        ? `，已更新 ${projectedCount} 只基金画像`
        : deletedCount
          ? `，已清理 ${deletedCount} 个失效画像`
          : ''
      setFolderMessage(`${payload.counts?.failed ? '扫描完成，部分文件需要处理' : '扫描完成'}${profileMessage}`)
      await Promise.all([loadMemos(selectedFolder.id), loadFolders(selectedFolder.id)])
    } catch (scanError) {
      setFolderMessage(scanError instanceof Error ? scanError.message : '扫描失败')
    } finally {
      setScanning(false)
    }
  }

  async function decideReview(review: PendingReview, action: 'confirmed' | 'rejected') {
    setReviewingId(review.id)
    setFolderMessage('')
    try {
      const response = await fetch(
        `/api/research-folders/reviews/${encodeURIComponent(review.report_id)}/${encodeURIComponent(review.id)}`,
        {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action }),
        },
      )
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload.error || '无法保存复核结果')
      setPendingReviews((items) => items.filter((item) => item.id !== review.id))
      const projectedCount = Number(payload.profile_projection?.projected_count || 0)
      const deletedCount = Number(payload.profile_projection?.deleted_count || 0)
      const linkedFundCount = Number(payload.linked_fund_count || 0)
      setFolderMessage(
        projectedCount
          ? `已保存，并更新 ${projectedCount} 只基金画像`
          : deletedCount
            ? `已保存，并清理 ${deletedCount} 个失效画像`
            : linkedFundCount
              ? `已确认经理，并关联 ${linkedFundCount} 只任期基金`
              : '已保存',
      )
      await loadMemos(selectedFolder?.id || '')
    } catch (reviewError) {
      setFolderMessage(reviewError instanceof Error ? reviewError.message : '无法保存复核结果')
    } finally {
      setReviewingId('')
    }
  }

  async function confirmHighConfidenceManagers() {
    if (!safeManagerReviewSummary.confirmable) return
    setBulkReviewing(true)
    setFolderMessage('')
    try {
      const response = await fetch('/api/research-folders/reviews/confirm-managers', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ folder_id: selectedFolder?.id || null, min_confidence: 0.88 }),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload.error || '批量确认失败')
      const multiManagerCount = Number(payload.multi_manager || 0)
      setFolderMessage(
        `已确认 ${Number(payload.confirmed || 0)} 份高置信经理归类，关联 ${Number(payload.linked_fund_count || 0)} 只任期基金`
        + (multiManagerCount ? `；其中 ${multiManagerCount} 份关联多位经理` : ''),
      )
      await Promise.all([loadMemos(selectedFolder?.id || ''), loadReviews(selectedFolder?.id || '')])
    } catch (bulkError) {
      setFolderMessage(bulkError instanceof Error ? bulkError.message : '批量确认失败')
    } finally {
      setBulkReviewing(false)
    }
  }

  async function confirmHighConfidenceLabels() {
    if (!highConfidenceLabelCount) return
    setBulkReviewing(true)
    setFolderMessage('')
    try {
      const response = await fetch('/api/research-folders/reviews/confirm-labels', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ folder_id: selectedFolder?.id || null, min_confidence: 0.9 }),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload.error || '批量确认失败')
      setFolderMessage(`已确认 ${Number(payload.confirmed || 0)} 项高置信分类与风格标签`)
      await Promise.all([loadMemos(selectedFolder?.id || ''), loadReviews(selectedFolder?.id || '')])
    } catch (bulkError) {
      setFolderMessage(bulkError instanceof Error ? bulkError.message : '批量确认失败')
    } finally {
      setBulkReviewing(false)
    }
  }

  async function openMemo(memo: ResearchMemo) {
    setSelectedMemo(memo)
    setDetailLoading(true)
    try {
      const response = await fetch(`/api/research-memos/${encodeURIComponent(memo.id)}`, { cache: 'no-store' })
      const payload = await response.json().catch(() => ({}))
      if (response.ok) setSelectedMemo(payload)
    } finally {
      setDetailLoading(false)
    }
  }

  return (
    <div className="space-y-7">
      <section className="grid gap-px overflow-hidden border-y border-[#dbe1dc] bg-[#dbe1dc] sm:grid-cols-4" aria-label="调研库概况">
        {[
          ['纪要', total, '已进入本地研究库'],
          ['已归类经理', classifiedManagerCount, '有唯一经理身份'],
          ['权益观点', domainCounts.equity, '涉及权益市场'],
          ['固收观点', domainCounts.fixed_income, '涉及债市与固收'],
        ].map(([label, value, note]) => (
          <div key={String(label)} className="bg-white px-5 py-4">
            <div className="text-xs text-[#718078]">{label}</div>
            <strong className="mt-1 block text-2xl text-[#183d33]">{value}</strong>
            <span className="mt-1 block text-[11px] text-[#8a948e]">{note}</span>
          </div>
        ))}
      </section>

      <div className="sticky top-12 z-20 flex min-w-0 items-center gap-1 overflow-x-auto border-y border-[#dbe1dc] bg-[#f7f9f7]/95 px-2 py-2 backdrop-blur" aria-label="调研库视图">
        {([
          ['managers', `经理库 ${managerProfiles.length}`],
          ['memos', `纪要 ${total}`],
          ['reviews', `待确认 ${reviewCounts.all}`],
        ] as Array<[LibraryView, string]>).map(([value, label]) => (
          <button key={value} type="button" onClick={() => setLibraryView(value)} className={`h-9 shrink-0 rounded-sm px-4 text-xs font-bold ${libraryView === value ? 'bg-[#173f35] text-white' : 'text-[#59675f] hover:bg-white'}`}>{label}</button>
        ))}
        <span className="ml-auto hidden shrink-0 px-2 text-[11px] text-[#7a8580] md:block">{selectedFolder?.name || '本地纪要库'} · 上次扫描 {formatDate(selectedFolder?.last_scan_at, true)}</span>
      </div>

      {libraryView === 'managers' ? (
        <ManagerResearchGrid
          profiles={visibleManagerProfiles}
          query={managerQuery}
          onQueryChange={setManagerQuery}
          onOpenMemos={(managerName) => {
            setSelectedManager(managerName)
            setLibraryView('memos')
          }}
          onOpenLatestMemo={(managerName) => {
            const memo = managerProfiles.find((profile) => profile.name === managerName)?.memos[0]
            if (memo) void openMemo(memo)
          }}
        />
      ) : null}

      {libraryView === 'memos' ? <>
      <section className="border border-[#dce3de] bg-[#f7faf7] px-5 py-5" aria-labelledby="wind-vane-heading">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 id="wind-vane-heading" className="text-lg font-bold">调研风向标</h2>
            <p className="mt-1 text-xs text-[#748078]">当前筛选范围内被谈及最多的主题{latestMemoDate ? ` · 最新纪要 ${formatDate(latestMemoDate)}` : ''}</p>
          </div>
          <div className="flex gap-2" aria-label="研究领域">
            {([
              ['', '全部', memos.length],
              ['equity', '权益', domainCounts.equity],
              ['fixed_income', '固收', domainCounts.fixed_income],
            ] as Array<[ResearchDomain, string, number]>).map(([value, label, count]) => (
              <button key={label} type="button" onClick={() => { setSelectedDomain(value); setSelectedTopic('') }} className={`rounded-full px-3 py-1.5 text-xs font-bold ${selectedDomain === value ? 'bg-[#173f35] text-white' : 'border border-[#cad5ce] bg-white text-[#53625b]'}`}>
                {label} {count}
              </button>
            ))}
          </div>
        </div>
        <div className="mt-4 grid gap-2 sm:grid-cols-5">
          {windVaneTopics.map(({ topic, count }, index) => (
            <button key={topic} type="button" onClick={() => setSelectedTopic(topic)} className="flex items-center justify-between border border-[#d7dfda] bg-white px-3 py-3 text-left hover:border-[#8dac9d]">
              <span><span className="mr-2 text-[11px] text-[#9a7a3d]">0{index + 1}</span><strong className="text-sm">{topic}</strong></span>
              <span className="text-xs text-[#718078]">{count}</span>
            </button>
          ))}
        </div>
      </section>

      <section className="space-y-4" aria-labelledby="viewpoint-heading">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 id="viewpoint-heading" className="text-xl font-bold">经理观点时间线</h2>
            <p className="mt-1 text-xs text-[#748078]">按经理、年份和主题筛选，点开查看原文</p>
          </div>
          <div className="text-xs text-[#748078]">当前 {filteredMemos.length} / {total} 份</div>
        </div>

        <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_12rem]">
          <label className="relative block">
            <Search className="pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-[#7d8882]" />
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索经理、基金公司、标题或关键词" className="h-12 w-full rounded-md border border-[#cfd6d0] bg-white pl-12 pr-4 text-sm outline-none focus:border-[#28745c]" />
          </label>
          <select value={selectedYear} onChange={(event) => setSelectedYear(event.target.value)} aria-label="发表年份" className="h-12 rounded-md border border-[#cfd6d0] bg-white px-3 text-sm outline-none focus:border-[#28745c]">
            <option value="">全部年份</option>
            {availableYears.map((year) => <option key={year} value={year}>{year} 年</option>)}
          </select>
        </div>

        <div className="flex flex-wrap gap-2" aria-label="观点主题">
          <button type="button" onClick={() => setSelectedTopic('')} className={`rounded-full px-3 py-1.5 text-xs font-bold ${!selectedTopic ? 'bg-[#173f35] text-white' : 'border border-[#ccd5cf] bg-white text-[#59675f]'}`}>全部主题</button>
          {topicCounts.map(({ topic, count }) => (
            <button key={topic} type="button" onClick={() => setSelectedTopic(topic)} className={`rounded-full px-3 py-1.5 text-xs font-bold ${selectedTopic === topic ? 'bg-[#173f35] text-white' : 'border border-[#ccd5cf] bg-white text-[#59675f]'}`}>
              {topic} {count}
            </button>
          ))}
        </div>

        <div className="flex gap-2 overflow-x-auto border-b border-[#dde3df] pb-3" aria-label="基金经理">
          <button type="button" onClick={() => setSelectedManager('')} className={`shrink-0 rounded-md px-3 py-2 text-sm ${!selectedManager ? 'bg-[#e3ece7] font-bold text-[#173f35]' : 'text-[#65716b] hover:bg-[#eef1ed]'}`}>全部经理 {memos.length}</button>
          {managerGroups.slice(0, 40).map((group) => (
            <button key={group.name} type="button" onClick={() => setSelectedManager(group.name)} className={`shrink-0 rounded-md px-3 py-2 text-sm ${selectedManager === group.name ? 'bg-[#e3ece7] font-bold text-[#173f35]' : 'text-[#65716b] hover:bg-[#eef1ed]'}`}>{group.name} {group.count}</button>
          ))}
        </div>

        {loading ? (
          <div className="flex min-h-64 items-center justify-center gap-3 border border-dashed border-[#cbd3cd] bg-white text-sm text-[#66726c]"><LoaderCircle className="h-5 w-5 animate-spin" />正在读取调研纪要</div>
        ) : filteredMemos.length === 0 ? (
          <div className="flex min-h-64 flex-col items-center justify-center border border-dashed border-[#cbd3cd] bg-white px-6 text-center"><FileSearch className="h-6 w-6 text-[#8b988f]" /><strong className="mt-3 text-sm">没有找到符合条件的观点</strong></div>
        ) : (
          <div className="divide-y divide-[#e3e8e4] border-y border-[#dbe1dc] bg-white">
            {filteredMemos.map((memo) => (
              <button key={memo.id} type="button" onClick={() => void openMemo(memo)} className="grid w-full gap-4 px-5 py-5 text-left transition hover:bg-[#f5f8f5] md:grid-cols-[11rem_minmax(0,1fr)_auto]">
                <div>
                  <strong className="block text-sm text-[#20362d]">{managerLabel(memo)}</strong>
                  {managerCompany(memo) ? <span className="mt-1 block text-xs text-[#68766f]">{managerCompany(memo)}</span> : null}
                  <span className="mt-2 inline-flex rounded-sm bg-[#eef3ef] px-2 py-1 text-[11px] text-[#52655b]">{memoDomainLabel(memo)}</span>
                  {managementYears(memo) ? <span className="mt-2 block text-[11px] text-[#859087]">管理 {managementYears(memo)}</span> : null}
                </div>
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2 text-xs text-[#718078]">
                    <span className="inline-flex items-center gap-1"><CalendarDays className="h-3.5 w-3.5" />{memoDateLabel(memo)}</span>
                    <span>{memo.source || '本地调研纪要'}</span>
                  </div>
                  <strong className="mt-2 block text-base text-[#1d2923]">{memo.title || '无标题纪要'}</strong>
                  <p className="mt-2 line-clamp-3 text-sm leading-7 text-[#66726c]">{memo.summary || '点击查看原文。'}</p>
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {(memo.viewpoint_topics || []).slice(0, 7).map((topic) => <span key={topic} className="rounded-sm bg-[#edf1ed] px-2 py-1 text-[11px] text-[#53625b]">#{topic}</span>)}
                    {memo.review_status === 'pending' ? <span className="rounded-sm bg-[#fff2d8] px-2 py-1 text-[11px] text-[#795b1d]">身份/风格待复核</span> : null}
                    {(() => {
                      const identity = memoIdentityLabel(memo)
                      if (!identity) return null
                      const className = identity.tone === 'verified'
                        ? 'rounded-sm bg-[#e7f0eb] px-2 py-1 text-[11px] text-[#2d6853]'
                        : identity.tone === 'warning'
                          ? 'rounded-sm bg-[#fff2d8] px-2 py-1 text-[11px] text-[#795b1d]'
                          : 'rounded-sm bg-[#eef1ef] px-2 py-1 text-[11px] text-[#607069]'
                      return <span className={className}>{identity.label}</span>
                    })()}
                  </div>
                </div>
                <ChevronRight className="hidden h-4 w-4 self-center text-[#849088] md:block" />
              </button>
            ))}
          </div>
        )}
      </section>
      </> : null}

      {folderMessage ? <div className="flex items-center gap-2 border border-[#e2d09d] bg-[#fff9ea] px-4 py-3 text-sm text-[#725921]"><CircleAlert className="h-4 w-4 shrink-0" />{folderMessage}</div> : null}
      {error ? <div className="border border-[#e5c98f] bg-[#fff8e8] px-5 py-4 text-sm text-[#78551c]">{error}</div> : null}

      {libraryView === 'reviews' ? (
        <div className="space-y-6 border-y border-[#dbe1dc] bg-[#f7f9f7] px-5 py-5">
      <section aria-labelledby="folder-heading" className="border border-[#dbe1dc] bg-white">
        <div className="grid gap-5 px-5 py-5 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
          <div>
            <div className="flex items-center justify-between gap-4">
              <h2 id="folder-heading" className="text-sm font-bold">本地文件夹路径</h2>
              <span className="text-xs text-[#748078]">上次扫描：{formatDate(selectedFolder?.last_scan_at, true)}</span>
            </div>
            {folders.length ? (
              <div className="mt-3 flex items-center gap-3">
                <label htmlFor="research-folder-select" className="shrink-0 text-xs font-bold text-[#59675f]">已连接</label>
                <select
                  id="research-folder-select"
                  value={selectedFolder?.id || ''}
                  onChange={(event) => selectFolder(event.target.value)}
                  className="h-10 min-w-0 flex-1 rounded-md border border-[#cfd6d0] bg-white px-3 text-sm outline-none focus:border-[#28745c]"
                >
                  {folders.map((folder) => <option key={folder.id} value={folder.id}>{folder.name}</option>)}
                </select>
              </div>
            ) : null}
            <div className="mt-3 flex min-w-0 flex-col gap-2 sm:flex-row">
              <label className="sr-only" htmlFor="research-folder-path">本地文件夹路径</label>
              <input
                id="research-folder-path"
                value={folderPath}
                onChange={(event) => setFolderPath(event.target.value)}
                placeholder="例如 /Users/你的名字/Documents/基金调研纪要"
                className="h-11 min-w-0 flex-1 rounded-md border border-[#cfd6d0] bg-[#fbfcfa] px-3 text-sm outline-none focus:border-[#28745c]"
              />
              <button type="button" onClick={() => void connectFolder()} disabled={connecting} className="inline-flex h-11 shrink-0 items-center justify-center gap-2 rounded-md border border-[#9aaba2] px-4 text-sm font-bold text-[#254c3e] hover:bg-[#eef4f0] disabled:opacity-50">
                {connecting ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <FolderOpen className="h-4 w-4" />}
                连接
              </button>
            </div>
          </div>
          <button type="button" onClick={() => void scanFolder()} disabled={!selectedFolder || scanning || folderLoading} className="inline-flex h-11 items-center justify-center gap-2 rounded-md bg-[#173f35] px-5 text-sm font-bold text-white hover:bg-[#225747] disabled:opacity-45">
            <RefreshCw className={`h-4 w-4 ${scanning ? 'animate-spin' : ''}`} />
            {scanning ? '正在扫描' : '扫描更新'}
          </button>
        </div>
        <div className="grid grid-cols-2 border-t border-[#e5e9e5] sm:grid-cols-4">
          {[
            ['新增', displayedCounts.created, 'text-[#28745c]'],
            ['已更新', displayedCounts.updated, 'text-[#27608a]'],
            ['未变化', displayedCounts.unchanged, 'text-[#65716b]'],
            ['失败', displayedCounts.failed, displayedCounts.failed ? 'text-[#a14e46]' : 'text-[#65716b]'],
          ].map(([label, value, color]) => (
            <div key={String(label)} className="border-r border-[#e5e9e5] px-4 py-3 last:border-r-0">
              <div className="text-[11px] text-[#7a8580]">{label}</div>
              <div className={`mt-1 text-xl font-bold ${color}`}>{value}</div>
            </div>
          ))}
        </div>
      </section>

      {llmUnavailableCount ? (
        <div className="border border-[#d7dee8] bg-[#f5f8fc] px-5 py-4 text-sm leading-6 text-[#46586c]">
          {llmUnavailableCount} 份纪要暂未完成 LLM 提取。当前只识别基金经理、基金代码和原文明示的分类/风格字段；不会把普通关键词当成已确认风格。
        </div>
      ) : null}

      <section aria-labelledby="review-heading" className="border-t border-[#dce1dc] pt-5">
        <div className="flex flex-wrap items-end justify-between gap-4 pb-3">
          <div><h2 id="review-heading" className="text-lg font-bold">待确认</h2><p className="mt-1 text-xs text-[#748078]">先确认基金经理；系统会自动关联 Tushare 已核验的任期基金。LLM 风格建议必须逐项确认。</p></div>
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-xs text-[#748078]">当前 {reviewGroups.length} 份纪要 · {visibleReviews.length} 项</span>
            <button type="button" onClick={() => void confirmHighConfidenceManagers()} disabled={!safeManagerReviewSummary.confirmable || bulkReviewing} className="inline-flex h-9 items-center gap-2 rounded-md border border-[#8fa99b] bg-white px-3 text-xs font-bold text-[#285d49] disabled:opacity-45">
              {bulkReviewing ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
              确认唯一经理 {safeManagerReviewSummary.confirmable}
            </button>
            {safeManagerReviewSummary.multiManager ? <span className="text-xs text-[#28745c]">多人纪要 {safeManagerReviewSummary.multiManager} 份将全部关联</span> : null}
            <button type="button" onClick={() => void confirmHighConfidenceLabels()} disabled={!highConfidenceLabelCount || bulkReviewing} className="inline-flex h-9 items-center gap-2 rounded-md border border-[#8fa99b] bg-white px-3 text-xs font-bold text-[#285d49] disabled:opacity-45">
              {bulkReviewing ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
              确认高置信标签 {highConfidenceLabelCount}
            </button>
          </div>
        </div>
        <div className="mb-3 flex flex-wrap gap-2" aria-label="待确认类型">
          {([
            ['manager', `经理归类 ${reviewCounts.manager}`],
            ['labels', `分类与风格 ${reviewCounts.labels}`],
            ['all', `全部 ${reviewCounts.all}`],
          ] as Array<[ReviewFilter, string]>).map(([value, label]) => (
            <button
              key={value}
              type="button"
              onClick={() => setReviewFilter(value)}
              className={`rounded-full px-3 py-1.5 text-xs font-bold ${reviewFilter === value ? 'bg-[#173f35] text-white' : 'border border-[#ccd5cf] bg-white text-[#59675f]'}`}
            >
              {label}
            </button>
          ))}
        </div>
        {reviewGroups.length ? (
          <div className="space-y-3">
            {reviewGroups.map((group) => (
              <details key={group.reportId} className="group border border-[#dbe1dc] bg-white">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-5 py-4">
                  <div className="min-w-0"><strong className="block truncate text-sm text-[#26362f]">{group.title}</strong><span className="mt-1 block truncate text-xs text-[#78837d]">{group.relativePath}</span></div>
                  <div className="flex shrink-0 items-center gap-3"><span className="text-xs text-[#748078]">{group.items.length} 项</span><ChevronRight className="h-4 w-4 text-[#748078] transition-transform group-open:rotate-90" /></div>
                </summary>
                <div className="divide-y divide-[#e8ece9] border-t border-[#e3e8e4]">
                  {group.items.map((review) => (
                    <article key={`${review.report_id}-${review.id}`} className="grid gap-4 px-5 py-4 md:grid-cols-[9rem_minmax(0,1fr)_auto] md:items-center">
                      <div><div className="text-[11px] text-[#78837d]">{reviewKind(review.kind)}</div><strong className="mt-1 block text-sm">{review.value}</strong><span className="mt-1 block text-[11px] text-[#78837d]">置信度 {Math.round(review.confidence * 100)}%</span>{['classification', 'style_label', 'tag'].includes(review.kind) ? <span className="mt-1 block text-[11px] text-[#78837d]">{review.scope === 'fund' ? `产品级：${(review.target_fund_ids || []).join('、')}` : '经理级，不直接进入基金推荐'}</span> : null}</div>
                      <blockquote className="min-w-0 border-l-2 border-[#d7b46a] pl-3 text-xs leading-6 text-[#68736d]">来源原文：{review.source_ref.excerpt}</blockquote>
                      <div className="flex gap-2">
                        <button type="button" aria-label={`确认${review.value}`} onClick={() => void decideReview(review, 'confirmed')} disabled={reviewingId === review.id} className="inline-flex h-9 items-center gap-1.5 rounded-md bg-[#e4efe9] px-3 text-xs font-bold text-[#245d49] hover:bg-[#d8e8df] disabled:opacity-50"><Check className="h-4 w-4" />确认</button>
                        <button type="button" aria-label={`拒绝${review.value}`} onClick={() => void decideReview(review, 'rejected')} disabled={reviewingId === review.id} className="inline-flex h-9 items-center gap-1.5 rounded-md border border-[#d6c9c5] px-3 text-xs font-bold text-[#8b4c43] hover:bg-[#faf1ef] disabled:opacity-50"><X className="h-4 w-4" />拒绝</button>
                      </div>
                    </article>
                  ))}
                </div>
              </details>
            ))}
          </div>
        ) : (
          <div className="flex h-20 items-center gap-2 border-y border-[#dbe1dc] bg-white px-5 text-sm text-[#718078]"><CheckCircle2 className="h-4 w-4 text-[#28745c]" />当前类型没有待确认内容</div>
        )}
      </section>
        </div>
      ) : null}

      {selectedMemo ? (
        <div className="fixed inset-0 z-[70] bg-[#17211d]/35 p-0 backdrop-blur-sm sm:p-6" role="dialog" aria-modal="true" aria-label="调研纪要详情">
          <div className="ml-auto flex h-full w-full max-w-3xl flex-col overflow-hidden bg-[#fbfcfa] shadow-2xl">
            <div className="flex items-start justify-between gap-4 border-b border-[#dbe1dc] px-5 py-4 sm:px-7">
              <div className="min-w-0">
                <div className="text-xs font-bold text-[#28745c]">{managerLabel(selectedMemo)} · {memoDateLabel(selectedMemo)}</div>
                <h2 className="mt-2 text-xl font-bold leading-snug">{selectedMemo.title}</h2>
                {selectedMemo.local_relative_path ? <p className="mt-2 break-all text-xs text-[#768179]">{selectedMemo.local_relative_path}</p> : null}
              </div>
              <button type="button" onClick={() => setSelectedMemo(null)} className="grid h-9 w-9 shrink-0 place-items-center rounded-md text-[#65716b] hover:bg-[#edf1ed]" aria-label="关闭详情"><X className="h-5 w-5" /></button>
            </div>
            <div className="flex-1 overflow-y-auto px-5 py-6 sm:px-7">
              {detailLoading ? <div className="flex items-center gap-2 text-sm text-[#66726c]"><LoaderCircle className="h-4 w-4 animate-spin" />读取原文</div> : null}
              <div className="flex flex-wrap gap-2">
                {(selectedMemo.viewpoint_topics || []).map((topic) => <span key={`topic-${topic}`} className="inline-flex items-center gap-1 rounded-sm bg-[#e8efeb] px-2 py-1 text-xs text-[#315e4d]"><Tag className="h-3 w-3" />观点主题：{topic}</span>)}
                {[...(selectedMemo.classifications || []), ...(selectedMemo.style_labels || []), ...(selectedMemo.tags || [])].map((tag, index) => <span key={`${tag}-${index}`} className="inline-flex items-center gap-1 rounded-sm border border-[#d8c9a9] bg-[#fff9ec] px-2 py-1 text-xs text-[#775f2d]"><Tag className="h-3 w-3" />已复核画像：{tag}</span>)}
              </div>
              {selectedMemo.summary ? <p className="mt-5 border-l-4 border-[#d7b46a] bg-[#fff9eb] px-4 py-3 text-sm leading-7 text-[#66583a]">{selectedMemo.summary}</p> : null}
              {['failed', 'unavailable'].includes(String(selectedMemo.llm_extraction_status || '')) ? (
                <div className="mt-4 border border-[#e2d09d] bg-[#fff9ea] px-4 py-3 text-xs leading-6 text-[#725921]">
                  LLM 提取暂不可用。当前只保留基金经理、基金代码和原文明示字段，所有结果仍需人工确认。
                </div>
              ) : null}
              {(selectedMemo.key_points || []).length ? <div className="mt-6 space-y-2">{(selectedMemo.key_points || []).map((point, index) => <div key={index} className="flex gap-2 text-sm leading-7 text-[#435149]"><CheckCircle2 className="mt-1.5 h-4 w-4 shrink-0 text-[#28745c]" />{point}</div>)}</div> : null}
              <div className="mt-7 whitespace-pre-wrap border-t border-[#dfe4df] pt-6 text-sm leading-8 text-[#334139]">{selectedMemo.content || '暂无可显示的原文。'}</div>
              {selectedMemo.source_hash ? <div className="mt-8 border-t border-[#e1e5e1] pt-4 text-[11px] text-[#7a8580]">来源校验：{selectedMemo.source_hash}</div> : null}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
