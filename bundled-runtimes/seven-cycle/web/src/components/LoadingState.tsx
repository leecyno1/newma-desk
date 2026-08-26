export default function LoadingState({ error }: { error?: string | null }) {
  return (
    <div className="loading-state">
      <div className={error ? 'loading-error' : 'loading-spinner'} />
      <strong>{error ? '研究数据不可用' : '正在加载真实研究数据'}</strong>
      <span>{error ?? '正在核对数据身份与发布门槛…'}</span>
    </div>
  )
}
