'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Bookmark, Bot, BookOpenText, Compass, House, Tags } from 'lucide-react'

const navigationItems = [
  {
    href: '/',
    icon: House,
    label: '首页',
    matches: ['/'],
  },
  {
    href: '/discover',
    icon: Compass,
    label: '找基金',
    matches: ['/discover', '/evaluation', '/compare', '/funds', '/market', '/companies'],
  },
  {
    href: '/watchlist',
    icon: Bookmark,
    label: '我的自选',
    matches: ['/watchlist'],
  },
  {
    href: '/research',
    icon: BookOpenText,
    label: '调研库',
    matches: ['/research', '/reports', '/managers'],
  },
  {
    href: '/analysis',
    icon: Bot,
    label: 'AI 分析',
    matches: ['/analysis'],
  },
  {
    href: '/recommendations',
    icon: Tags,
    label: '基金推荐',
    matches: ['/recommendations'],
  },
] as const

function isActive(pathname: string, matches: readonly string[]) {
  return matches.some((path) => pathname === path || pathname.startsWith(`${path}/`))
}

export default function AppNavigation() {
  const pathname = usePathname()

  return (
    <>
      <header className="sticky top-0 z-40 border-b border-[#dce1dc] bg-[#fbfcfa]/95 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-[1440px] items-center justify-between px-4 sm:px-6 lg:px-10">
          <Link href="/" className="flex items-center gap-3" aria-label="选基助手首页">
            <span className="grid h-9 w-9 place-items-center rounded-md bg-[#173f35] text-sm font-black text-white">基</span>
            <span>
              <span className="block text-[15px] font-bold leading-none text-[#17211d]">选基助手</span>
              <span className="mt-1 hidden text-[11px] text-[#748079] sm:block">看懂基金，再做选择</span>
            </span>
          </Link>

          <nav className="hidden items-center gap-1 lg:flex" aria-label="主要导航">
            {navigationItems.map((item) => {
              const Icon = item.icon
              const active = isActive(pathname, item.matches)
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={active ? 'page' : undefined}
                  className={`flex h-10 items-center gap-2 rounded-md px-4 text-sm font-semibold transition-colors ${
                    active
                      ? 'bg-[#e3ece7] text-[#173f35]'
                      : 'text-[#65716b] hover:bg-[#eef1ed] hover:text-[#26332d]'
                  }`}
                >
                  <Icon className="h-4 w-4" aria-hidden="true" />
                  {item.label}
                </Link>
              )
            })}
          </nav>

          <div className="hidden items-center gap-2 text-xs text-[#748079] sm:flex">
            <span className="h-2 w-2 rounded-full bg-[#2d8a68]" />
            本地基金库
          </div>
        </div>
      </header>

      <nav className="fixed inset-x-3 bottom-3 z-50 grid grid-cols-6 border border-[#d9ded9] bg-[#fbfcfa]/95 p-1.5 shadow-[0_12px_40px_rgba(25,40,32,0.16)] backdrop-blur-xl lg:hidden" aria-label="移动端主要导航">
        {navigationItems.map((item) => {
          const Icon = item.icon
          const active = isActive(pathname, item.matches)
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? 'page' : undefined}
              className={`flex min-w-0 flex-col items-center justify-center gap-1 rounded-md px-1 py-2 text-[11px] font-semibold ${
                active ? 'bg-[#e3ece7] text-[#173f35]' : 'text-[#738078]'
              }`}
            >
              <Icon className="h-4 w-4" aria-hidden="true" />
              <span className="truncate">{item.label}</span>
            </Link>
          )
        })}
      </nav>
    </>
  )
}
