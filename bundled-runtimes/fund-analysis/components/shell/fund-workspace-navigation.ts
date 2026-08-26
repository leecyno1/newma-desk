import {
  BadgeCheck,
  Bookmark,
  BookMarked,
  Bot,
  BookOpenText,
  ChartNoAxesCombined,
  ClipboardCheck,
  ClipboardList,
  Compass,
  Database,
  GitCompareArrows,
  House,
  Layers,
  Tags,
  Users,
  type LucideIcon,
} from 'lucide-react'

export type FundWorkspaceNavigationItem = {
  href: string
  label: string
  shortLabel: string
  icon: LucideIcon
  matches: readonly string[]
}

export type FundWorkspaceNavigationGroup = {
  label: string
  items: readonly FundWorkspaceNavigationItem[]
}

export const fundWorkspaceNavigation: readonly FundWorkspaceNavigationGroup[] = [
  {
    label: '发现',
    items: [
      { href: '/', label: '研究概览', shortLabel: '概览', icon: House, matches: ['/'] },
      { href: '/discover', label: '基金浏览器', shortLabel: '浏览', icon: Compass, matches: ['/discover', '/funds', '/market', '/companies'] },
      { href: '/managers', label: '基金经理', shortLabel: '经理', icon: Users, matches: ['/managers'] },
    ],
  },
  {
    label: '研究',
    items: [
      { href: '/compare', label: '同类比较', shortLabel: '比较', icon: GitCompareArrows, matches: ['/compare'] },
      { href: '/evaluation', label: '评价与分类', shortLabel: '评价', icon: BadgeCheck, matches: ['/evaluation'] },
      { href: '/research/pending', label: '待确认收件箱', shortLabel: '待确认', icon: ClipboardCheck, matches: ['/research/pending'] },
      { href: '/research', label: '调研纪要', shortLabel: '纪要', icon: BookOpenText, matches: ['/research', '/reports'] },
      { href: '/analysis/advanced', label: '业绩归因', shortLabel: '归因', icon: ChartNoAxesCombined, matches: ['/analysis/advanced', '/barra', '/brinson'] },
    ],
  },
  {
    label: '我的',
    items: [
      { href: '/workbench', label: '研究工作台', shortLabel: '工作台', icon: ClipboardList, matches: ['/workbench'] },
      { href: '/portfolio', label: '基金组合', shortLabel: '组合', icon: Layers, matches: ['/portfolio'] },
      { href: '/theses', label: '投资论点', shortLabel: '论点', icon: BookMarked, matches: ['/theses'] },
      { href: '/watchlist', label: '自选与候选', shortLabel: '自选', icon: Bookmark, matches: ['/watchlist'] },
      { href: '/analysis', label: 'AI 分析', shortLabel: 'AI', icon: Bot, matches: ['/analysis'] },
      { href: '/recommendations', label: '候选基金', shortLabel: '候选', icon: Tags, matches: ['/recommendations'] },
    ],
  },
]

export const fundWorkspaceDataNavigation: FundWorkspaceNavigationItem = {
  href: '/evidence-coverage',
  label: '数据与方法',
  shortLabel: '数据',
  icon: Database,
  matches: ['/evidence-coverage'],
}

export function isFundWorkspaceItemActive(
  pathname: string,
  item: FundWorkspaceNavigationItem,
) {
  // First check if this item matches at all
  const selfMatches = item.matches.some((match) => (
    match === '/'
      ? pathname === '/'
      : pathname === match || pathname.startsWith(`${match}/`)
  ))
  if (!selfMatches) return false

  // Deduplicate against more specific sibling items: only mark active if no
  // other registered item claims a longer prefix of the same pathname. This
  // prevents e.g. /research/pending activating both 「调研纪要」and 「待确认收件箱」.
  const allItems = [
    ...fundWorkspaceNavigation.flatMap((group) => group.items),
    fundWorkspaceDataNavigation,
  ]
  const bestLength = allItems.reduce((best, candidate) => {
    for (const match of candidate.matches) {
      const matches = match === '/'
        ? pathname === '/'
        : pathname === match || pathname.startsWith(`${match}/`)
      if (matches && match.length > best) return match.length
    }
    return best
  }, 0)
  return item.matches.some((match) => {
    const matches = match === '/'
      ? pathname === '/'
      : pathname === match || pathname.startsWith(`${match}/`)
    return matches && match.length === bestLength
  })
}

export function currentFundWorkspaceItem(pathname: string) {
  const allItems = [
    ...fundWorkspaceNavigation.flatMap((group) => group.items),
    fundWorkspaceDataNavigation,
  ]
  return allItems.find((item) => isFundWorkspaceItemActive(pathname, item))
}
