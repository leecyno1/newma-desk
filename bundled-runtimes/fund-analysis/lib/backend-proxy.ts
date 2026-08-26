import { NextResponse } from 'next/server'
import { backendApiBaseUrl } from '@/lib/backend-api'

/**
 * 通用后端代理：把 Next.js 请求透传到 FastAPI 后端。
 * 用于研究工作台类只读 + 写入接口（anomalies / watches / research-queue / postmortems）。
 */
export async function proxyGet(basePath: string, request: Request) {
  const url = new URL(request.url)
  const search = url.searchParams.toString()
  const suffix = search ? `?${search}` : ''
  try {
    const response = await fetch(`${backendApiBaseUrl}${basePath}${suffix}`, { cache: 'no-store' })
    const payload = await response.json().catch(() => ({}))
    return NextResponse.json(payload, { status: response.status })
  } catch (error) {
    return NextResponse.json({ error: (error as Error).message || 'backend unavailable' }, { status: 503 })
  }
}

export async function proxyPost(basePath: string, request: Request) {
  const body = await request.json().catch(() => ({}))
  try {
    const response = await fetch(`${backendApiBaseUrl}${basePath}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    const payload = await response.json().catch(() => ({}))
    return NextResponse.json(payload, { status: response.status })
  } catch (error) {
    return NextResponse.json({ error: (error as Error).message || 'backend unavailable' }, { status: 503 })
  }
}

export async function proxyPatch(basePath: string, request: Request) {
  const body = await request.json().catch(() => ({}))
  try {
    const response = await fetch(`${backendApiBaseUrl}${basePath}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    const payload = await response.json().catch(() => ({}))
    return NextResponse.json(payload, { status: response.status })
  } catch (error) {
    return NextResponse.json({ error: (error as Error).message || 'backend unavailable' }, { status: 503 })
  }
}

export async function proxyPut(basePath: string, request: Request) {
  const body = await request.json().catch(() => ({}))
  try {
    const response = await fetch(`${backendApiBaseUrl}${basePath}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    const payload = await response.json().catch(() => ({}))
    return NextResponse.json(payload, { status: response.status })
  } catch (error) {
    return NextResponse.json({ error: (error as Error).message || 'backend unavailable' }, { status: 503 })
  }
}

export async function proxyDelete(basePath: string) {
  try {
    const response = await fetch(`${backendApiBaseUrl}${basePath}`, { method: 'DELETE' })
    const payload = await response.json().catch(() => ({}))
    return NextResponse.json(payload, { status: response.status })
  } catch (error) {
    return NextResponse.json({ error: (error as Error).message || 'backend unavailable' }, { status: 503 })
  }
}
