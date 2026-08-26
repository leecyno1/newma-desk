// 统一错误处理工具

export class AppError extends Error {
  constructor(
    message: string,
    public statusCode: number = 500,
    public code?: string
  ) {
    super(message)
    this.name = 'AppError'
  }
}

export class ValidationError extends AppError {
  constructor(message: string) {
    super(message, 400, 'VALIDATION_ERROR')
    this.name = 'ValidationError'
  }
}

export class NotFoundError extends AppError {
  constructor(resource: string) {
    super(`${resource}不存在`, 404, 'NOT_FOUND')
    this.name = 'NotFoundError'
  }
}

export class UnauthorizedError extends AppError {
  constructor(message: string = '未授权') {
    super(message, 401, 'UNAUTHORIZED')
    this.name = 'UnauthorizedError'
  }
}

export class ExternalServiceError extends AppError {
  constructor(service: string, message?: string) {
    super(message || `${service}服务异常`, 503, 'EXTERNAL_SERVICE_ERROR')
    this.name = 'ExternalServiceError'
  }
}

// API 错误响应格式化
export function formatErrorResponse(error: unknown) {
  if (error instanceof AppError) {
    return {
      error: error.message,
      code: error.code,
      statusCode: error.statusCode
    }
  }

  if (error instanceof Error) {
    return {
      error: error.message,
      code: 'INTERNAL_ERROR',
      statusCode: 500
    }
  }

  return {
    error: '未知错误',
    code: 'UNKNOWN_ERROR',
    statusCode: 500
  }
}

// API 路由错误处理包装器
export function withErrorHandler(
  handler: (request: Request, context?: any) => Promise<Response>
) {
  return async (request: Request, context?: any) => {
    try {
      return await handler(request, context)
    } catch (error) {
      console.error('API Error:', error)

      const errorResponse = formatErrorResponse(error)

      return new Response(
        JSON.stringify(errorResponse),
        {
          status: errorResponse.statusCode,
          headers: { 'Content-Type': 'application/json' }
        }
      )
    }
  }
}

// 前端错误提示
export function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message
  }

  if (typeof error === 'string') {
    return error
  }

  return '操作失败，请稍后重试'
}

// 错误日志记录
export function logError(error: unknown, context?: Record<string, any>) {
  const timestamp = new Date().toISOString()
  const errorInfo = {
    timestamp,
    error: error instanceof Error ? {
      name: error.name,
      message: error.message,
      stack: error.stack
    } : error,
    context
  }

  console.error('[Error Log]', JSON.stringify(errorInfo, null, 2))

  // 这里可以集成第三方错误追踪服务（如 Sentry）
  // if (process.env.SENTRY_DSN) {
  //   Sentry.captureException(error, { extra: context })
  // }
}
