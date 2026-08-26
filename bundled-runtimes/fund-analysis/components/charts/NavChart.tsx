'use client'

import { useState, useEffect, useCallback } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer
} from 'recharts'

interface NavData {
  date: string
  nav: number
  navAdj?: number
}

interface NavChartProps {
  fundCode: string
  fundName?: string
  days?: number
  height?: number
}

export default function NavChart({
  fundCode,
  fundName,
  days = 365,
  height = 400
}: NavChartProps) {
  const [data, setData] = useState<NavData[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchNavData = useCallback(async () => {
    setLoading(true)
    setError(null)

    try {
      // 计算日期范围
      const endDate = new Date()
      const startDate = new Date()
      startDate.setDate(startDate.getDate() - days)

      const params = new URLSearchParams({
        fundCode,
        startDate: startDate.toISOString().split('T')[0],
        endDate: endDate.toISOString().split('T')[0]
      })

      const response = await fetch(`/api/funds/nav?${params}`)

      if (!response.ok) {
        throw new Error('获取净值数据失败')
      }

      const result = await response.json()

      // 转换数据格式
      const formattedData = result.data?.map((item: any) => ({
        date: new Date(item.date).toLocaleDateString('zh-CN'),
        nav: Number(Number(item.nav).toFixed(4)),
        navAdj: item.navAdj ? Number(Number(item.navAdj).toFixed(4)) : undefined
      })) || []

      if (formattedData.length === 0) {
        throw new Error('暂无真实净值数据')
      }

      setData(formattedData)
    } catch (err) {
      console.error('获取净值数据失败:', err)
      setError(err instanceof Error ? err.message : '获取数据失败')
      setData([])
    } finally {
      setLoading(false)
    }
  }, [days, fundCode])

  useEffect(() => {
    void fetchNavData()
  }, [fetchNavData])

  if (loading) {
    return (
      <div className="flex items-center justify-center" style={{ height }}>
        <div className="text-gray-500">加载净值数据...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center rounded-2xl border border-amber-100 bg-amber-50 px-4 text-center" style={{ height }} data-testid="nav-chart-real-data-required">
        <div className="text-red-500 mb-2">{error}</div>
        <div className="text-sm text-amber-700">未展示净值曲线；请先同步真实净值数据。系统不会用随机曲线替代真实净值。</div>
      </div>
    )
  }

  return (
    <div className="w-full">
      <div className="mb-4">
        <h3 className="text-lg font-semibold text-gray-900">
          {fundName || fundCode} 净值走势
        </h3>
        <p className="text-sm text-gray-500">
          最近 {days} 天
        </p>
      </div>

      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 12 }}
            tickLine={false}
            axisLine={false}
          />
          <YAxis
            tick={{ fontSize: 12 }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(value) => Number(value).toFixed(2)}
          />
          <Tooltip
            labelStyle={{ color: '#374151' }}
            formatter={(value: any, name: any) => [
              Number(value).toFixed(4),
              name === 'nav' ? '单位净值' : '累计净值'
            ]}
          />
          <Legend />
          <Line
            type="monotone"
            dataKey="nav"
            stroke="#3B82F6"
            strokeWidth={2}
            dot={false}
            name="单位净值"
          />
          {data.some(item => item.navAdj) && (
            <Line
              type="monotone"
              dataKey="navAdj"
              stroke="#10B981"
              strokeWidth={2}
              dot={false}
              name="累计净值"
            />
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
