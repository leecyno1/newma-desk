// 加载状态组件

export function LoadingSpinner({ size = 'md' }: { size?: 'sm' | 'md' | 'lg' }) {
  const sizeClasses = {
    sm: 'w-4 h-4',
    md: 'w-8 h-8',
    lg: 'w-12 h-12'
  }

  return (
    <div className="flex items-center justify-center">
      <div className={`${sizeClasses[size]} border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin`} />
    </div>
  )
}

export function LoadingOverlay({ message }: { message?: string }) {
  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg p-6 flex flex-col items-center">
        <LoadingSpinner size="lg" />
        {message && (
          <p className="mt-4 text-sm text-gray-600">{message}</p>
        )}
      </div>
    </div>
  )
}

export function LoadingPage() {
  return (
    <div className="flex items-center justify-center min-h-screen">
      <div className="text-center">
        <LoadingSpinner size="lg" />
        <p className="mt-4 text-sm text-gray-500">加载中...</p>
      </div>
    </div>
  )
}

// 骨架屏组件
export function SkeletonLine({ width = '100%' }: { width?: string }) {
  return (
    <div
      className="h-4 bg-gray-200 rounded animate-pulse"
      style={{ width }}
    />
  )
}

export function SkeletonCard() {
  return (
    <div className="bg-white rounded-lg shadow p-6 space-y-4">
      <SkeletonLine width="60%" />
      <SkeletonLine width="100%" />
      <SkeletonLine width="80%" />
      <div className="flex gap-4 mt-4">
        <SkeletonLine width="30%" />
        <SkeletonLine width="30%" />
      </div>
    </div>
  )
}

export function SkeletonTable({ rows = 5 }: { rows?: number }) {
  return (
    <div className="bg-white rounded-lg shadow overflow-hidden">
      <div className="p-4 border-b border-gray-200">
        <SkeletonLine width="40%" />
      </div>
      <div className="divide-y divide-gray-200">
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} className="p-4 flex gap-4">
            <SkeletonLine width="20%" />
            <SkeletonLine width="30%" />
            <SkeletonLine width="15%" />
            <SkeletonLine width="15%" />
          </div>
        ))}
      </div>
    </div>
  )
}

export function SkeletonList({ items = 5 }: { items?: number }) {
  return (
    <div className="space-y-4">
      {Array.from({ length: items }).map((_, i) => (
        <SkeletonCard key={i} />
      ))}
    </div>
  )
}
