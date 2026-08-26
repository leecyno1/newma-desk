'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { ArrowLeft, Upload, FileText, CheckCircle, AlertCircle } from 'lucide-react'

export default function UploadReportPage() {
  const router = useRouter()
  const [file, setFile] = useState<File | null>(null)
  const [managerId, setManagerId] = useState('')
  const [source, setSource] = useState('用户上传')
  const [tags, setTags] = useState('')
  const [uploading, setUploading] = useState(false)
  const [result, setResult] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0]
    if (selectedFile) {
      setFile(selectedFile)
      setError(null)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!file) {
      setError('请选择文件')
      return
    }

    setUploading(true)
    setError(null)
    setResult(null)

    try {
      const formData = new FormData()
      formData.append('file', file)
      if (managerId) formData.append('managerId', managerId)
      if (source) formData.append('source', source)
      if (tags) formData.append('tags', tags)

      const response = await fetch('/api/reports/upload', {
        method: 'POST',
        body: formData
      })

      const data = await response.json()

      if (!response.ok) {
        throw new Error(data.error || '上传失败')
      }

      setResult(data)

      // 3秒后跳转到报告详情页
      setTimeout(() => {
        router.push(`/reports/${data.report.id}`)
      }, 3000)
    } catch (err) {
      console.error('上传失败:', err)
      setError(err instanceof Error ? err.message : '上传失败')
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <Link
        href="/reports"
        className="inline-flex items-center text-gray-600 hover:text-gray-900"
      >
        <ArrowLeft className="w-4 h-4 mr-2" />
        返回列表
      </Link>

      <div className="bg-white rounded-lg shadow p-6">
        <form onSubmit={handleSubmit} className="space-y-6">
          {/* 文件上传 */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              选择文件 *
            </label>
            <div className="border-2 border-dashed border-gray-300 rounded-lg p-6 text-center hover:border-blue-400 transition-colors">
              <input
                type="file"
                accept=".pdf,.doc,.docx,.txt,.md"
                onChange={handleFileChange}
                className="hidden"
                id="file-upload"
              />
              <label
                htmlFor="file-upload"
                className="cursor-pointer flex flex-col items-center"
              >
                <Upload className="w-12 h-12 text-gray-400 mb-3" />
                <p className="text-sm text-gray-600 mb-1">
                  点击选择文件或拖拽文件到此处
                </p>
                <p className="text-xs text-gray-500">
                  支持 PDF、Word、TXT、Markdown 格式
                </p>
              </label>
            </div>
            {file && (
              <div className="mt-3 flex items-center text-sm text-gray-600">
                <FileText className="w-4 h-4 mr-2" />
                <span>{file.name}</span>
                <span className="ml-2 text-gray-400">
                  ({(file.size / 1024).toFixed(2)} KB)
                </span>
              </div>
            )}
          </div>

          {/* 基金经理 */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              关联基金经理 ID（可选）
            </label>
            <input
              type="text"
              value={managerId}
              onChange={(e) => setManagerId(e.target.value)}
              placeholder="输入基金经理 ID"
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>

          {/* 来源 */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              报告来源
            </label>
            <input
              type="text"
              value={source}
              onChange={(e) => setSource(e.target.value)}
              placeholder="例如：公司调研、券商报告"
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>

          {/* 标签 */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              标签（可选）
            </label>
            <input
              type="text"
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              placeholder="用逗号分隔，例如：价值投资,成长股,医药"
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
            <p className="mt-1 text-xs text-gray-500">
              AI 会自动提取标签，您也可以手动添加
            </p>
          </div>

          {/* 提交按钮 */}
          <div className="flex gap-4">
            <button
              type="submit"
              disabled={!file || uploading}
              className="flex-1 flex items-center justify-center px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {uploading ? (
                <>
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2" />
                  上传中...
                </>
              ) : (
                <>
                  <Upload className="w-4 h-4 mr-2" />
                  上传报告
                </>
              )}
            </button>
            <Link
              href="/reports"
              className="px-6 py-3 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors"
            >
              取消
            </Link>
          </div>
        </form>

        {/* 错误提示 */}
        {error && (
          <div className="mt-6 p-4 bg-red-50 border border-red-200 rounded-lg flex items-start">
            <AlertCircle className="w-5 h-5 text-red-600 mr-3 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-medium text-red-800">上传失败</p>
              <p className="text-sm text-red-600 mt-1">{error}</p>
            </div>
          </div>
        )}

        {/* 成功提示 */}
        {result && (
          <div className="mt-6 p-4 bg-green-50 border border-green-200 rounded-lg">
            <div className="flex items-start mb-3">
              <CheckCircle className="w-5 h-5 text-green-600 mr-3 flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-medium text-green-800">上传成功</p>
                <p className="text-sm text-green-600 mt-1">
                  正在跳转到报告详情页...
                </p>
              </div>
            </div>
            {result.metadata && (
              <div className="mt-3 pl-8 space-y-2 text-sm">
                <p className="text-gray-700">
                  <span className="font-medium">标题：</span>
                  {result.metadata.title}
                </p>
                {result.metadata.tags.length > 0 && (
                  <p className="text-gray-700">
                    <span className="font-medium">标签：</span>
                    {result.metadata.tags.join(', ')}
                  </p>
                )}
                {result.metadata.summary && (
                  <p className="text-gray-700">
                    <span className="font-medium">摘要：</span>
                    {result.metadata.summary.substring(0, 100)}...
                  </p>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
