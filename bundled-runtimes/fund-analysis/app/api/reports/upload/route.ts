import { NextRequest, NextResponse } from 'next/server'
import { backendApiBaseUrl } from '@/lib/backend-api'

interface ReportMetadata {
  title: string
  reportDate: string
  managerName?: string
  managerId?: string
  source: string
  tags: string[]
  classifications: string[]
  styleLabels: string[]
  summary: string
  keyPoints: string[]
  fundIds: string[]
}

function sanitizeText(value: unknown, maxLength = 500) {
  return String(value || '')
    .replace(/[\u0000-\u001F\u007F-\u009F]/gu, ' ')
    .replace(/\s+/gu, ' ')
    .trim()
    .slice(0, maxLength)
}

export async function POST(request: NextRequest) {
  try {
    const formData = await request.formData()
    const file = formData.get('file') as File | null
    const managerId = formData.get('managerId') as string | null
    const source = formData.get('source') as string || '用户上传'
    const tags = formData.get('tags') as string || ''

    if (!file) {
      return NextResponse.json(
        { error: '请上传文件' },
        { status: 400 }
      )
    }

    // 提取文件内容
    const fileName = file.name
    const fileExtension = fileName.split('.').pop()?.toLowerCase()
    let content = ''

    if (fileExtension === 'txt' || fileExtension === 'md') {
      content = await file.text()
    } else if (fileExtension === 'pdf') {
      // PDF 解析 - 使用 buffer 转文本
      const buffer = Buffer.from(await file.arrayBuffer())
      content = await extractPdfText(buffer)
    } else if (fileExtension === 'docx' || fileExtension === 'doc') {
      // Word 文档解析
      const buffer = Buffer.from(await file.arrayBuffer())
      content = await extractDocxText(buffer)
    } else {
      return NextResponse.json(
        { error: `不支持的文件格式: ${fileExtension}` },
        { status: 400 }
      )
    }

    if (!content.trim()) {
      return NextResponse.json(
        { error: '文件内容为空' },
        { status: 400 }
      )
    }

    // 使用 Claude API 提取结构化信息
    const metadata = await extractReportMetadata(content, fileName)

    // 解析标签
    const managerName = sanitizeText(metadata.managerName, 80)
    const resolvedManagerId = sanitizeText(managerId, 120) || await resolveManagerId(managerName)
    const classificationList = (metadata.classifications || []).map((item) => sanitizeText(item, 80)).filter(Boolean)
    const styleLabels = (metadata.styleLabels || []).map((item) => sanitizeText(item, 80)).filter(Boolean)
    const tagList = (tags
      ? tags.split(',').map(t => t.trim()).filter(Boolean)
      : [...metadata.tags, ...classificationList, ...styleLabels]
    ).map((tag) => sanitizeText(tag, 80)).filter(Boolean)

    const title = metadata.title || fileName.replace(/\.[^.]+$/, '')
    const reportDate = metadata.reportDate || new Date().toISOString().split('T')[0]
    const summary = sanitizeText(metadata.summary || content.slice(0, 500), 500)
    const cleanSource = sanitizeText(source || metadata.source, 120) || '用户上传'
    const keyPoints = (metadata.keyPoints || []).map((point) => sanitizeText(point, 160)).filter(Boolean)
    const saveResponse = await fetch(`${backendApiBaseUrl}/api/research-reports/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        manager_id: resolvedManagerId || metadata.managerId || '',
        manager_name: managerName,
        title,
        report_date: reportDate,
        source: cleanSource,
        content,
        summary,
        tags: tagList,
        classifications: classificationList,
        style_labels: styleLabels,
        key_points: keyPoints,
        fund_ids: metadata.fundIds || [],
      }),
    })
    const savedPayload = await saveResponse.json().catch(() => ({}))
    if (!saveResponse.ok) {
      throw new Error(savedPayload.detail || savedPayload.error || '调研报告保存失败')
    }

    const report = {
      id: savedPayload.id,
      title,
      reportDate,
      source: cleanSource,
      tags: tagList,
      summary,
      keyPoints,
      managerId: resolvedManagerId || metadata.managerId || null,
      managerName: managerName || null,
      classifications: classificationList,
      styleLabels,
    }

    return NextResponse.json({
      success: true,
      report,
      metadata: {
        title: metadata.title,
        tags: tagList,
        managerName,
        classifications: classificationList,
        styleLabels,
        summary,
        keyPoints,
      }
    }, { status: 201 })
  } catch (error) {
    console.error('上传调研报告失败:', error)
    return NextResponse.json(
      { error: '上传调研报告失败', details: error instanceof Error ? error.message : '未知错误' },
      { status: 500 }
    )
  }
}

async function resolveManagerId(managerName: string) {
  if (!managerName) return ''
  try {
    const params = new URLSearchParams({ keyword: managerName, page: '1', page_size: '10' })
    const response = await fetch(`${backendApiBaseUrl}/api/managers/?${params.toString()}`, { cache: 'no-store' })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) return ''
    const candidates = Array.isArray(payload.managers) ? payload.managers : []
    const exact = candidates.find((item: Record<string, unknown>) => sanitizeText(item.name, 80) === managerName)
    return sanitizeText(exact?.manager_id || exact?.wind_code, 120)
  } catch {
    return ''
  }
}

// 提取 PDF 文本内容
async function extractPdfText(buffer: Buffer): Promise<string> {
  try {
    // 动态导入 pdf-parse (server-side only)
    const pdfModule = await import('pdf-parse')
    type PdfParse = (input: Buffer) => Promise<{ text: string }>
    const typedPdfModule = pdfModule as unknown as { default?: PdfParse; PDFParse?: PdfParse } | PdfParse
    const pdfParse = typeof typedPdfModule === 'function'
      ? typedPdfModule
      : typedPdfModule.default || typedPdfModule.PDFParse
    if (!pdfParse) throw new Error('pdf-parse 导出不可用')
    const data = await pdfParse(buffer)
    return data.text
  } catch (error) {
    console.error('PDF 解析失败:', error)
    // 如果 pdf-parse 未安装，返回错误提示
    return `[PDF 文件 - ${buffer.length} 字节 - 需要安装 pdf-parse 依赖]`
  }
}

// 提取 Word 文档文本内容
async function extractDocxText(buffer: Buffer): Promise<string> {
  try {
    const mammoth = await import('mammoth')
    const result = await mammoth.extractRawText({ buffer })
    return result.value
  } catch (error) {
    console.error('DOCX 解析失败:', error)
    return `[Word 文档 - ${buffer.length} 字节 - 需要安装 mammoth 依赖]`
  }
}

// 使用 Claude API 提取报告元数据
async function extractReportMetadata(
  content: string,
  fileName: string
): Promise<ReportMetadata> {
  const apiKey = process.env.ANTHROPIC_API_KEY

  // 如果没有配置 Claude API，返回基础元数据
  if (!apiKey) {
    return {
      title: fileName.replace(/\.[^.]+$/, ''),
      reportDate: new Date().toISOString().split('T')[0],
      source: '用户上传',
      tags: [],
      classifications: [],
      styleLabels: [],
      summary: content.substring(0, 500),
      keyPoints: [],
      fundIds: []
    }
  }

  try {
    const Anthropic = (await import('@anthropic-ai/sdk')).default
    const anthropic = new Anthropic({ apiKey })

    // 截取前 3000 字符用于提取元数据
    const contentExcerpt = content.substring(0, 3000)

    const message = await anthropic.messages.create({
      model: 'claude-3-5-sonnet-20241022',
      max_tokens: 1024,
      messages: [
        {
          role: 'user',
          content: `请从以下调研报告中提取结构化信息，返回纯 JSON（不要 markdown 代码块）：

报告内容：
${contentExcerpt}

返回以下格式的 JSON：
{
  "title": "报告标题",
  "reportDate": "YYYY-MM-DD",
  "managerName": "基金经理姓名（如果有）",
  "source": "报告来源",
  "tags": ["标签1", "标签2"],
  "classifications": ["基金类别或策略类别"],
  "styleLabels": ["成长", "大盘", "低换手"],
  "summary": "一段话摘要（200字以内）",
  "keyPoints": ["要点1", "要点2", "要点3"]
}`
        }
      ]
    })

    const responseText = message.content[0].type === 'text'
      ? message.content[0].text
      : ''

    // 尝试解析 JSON
    const jsonMatch = responseText.match(/\{[\s\S]*\}/)
    if (jsonMatch) {
      const parsed = JSON.parse(jsonMatch[0])
      return {
        title: parsed.title || fileName.replace(/\.[^.]+$/, ''),
        reportDate: parsed.reportDate || new Date().toISOString().split('T')[0],
        managerName: parsed.managerName,
        source: parsed.source || '用户上传',
        tags: parsed.tags || [],
        classifications: parsed.classifications || [],
        styleLabels: parsed.styleLabels || [],
        summary: parsed.summary || content.substring(0, 500),
        keyPoints: parsed.keyPoints || [],
        fundIds: []
      }
    }
  } catch (error) {
    console.error('Claude API 元数据提取失败:', error)
  }

  // 回退到基础元数据
  return {
    title: fileName.replace(/\.[^.]+$/, ''),
    reportDate: new Date().toISOString().split('T')[0],
    source: '用户上传',
    tags: [],
    classifications: [],
    styleLabels: [],
    summary: content.substring(0, 500),
    keyPoints: [],
    fundIds: []
  }
}
