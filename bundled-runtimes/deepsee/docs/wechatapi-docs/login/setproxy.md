# 无感切换代理ip

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /login/setProxy:
    post:
      summary: 无感切换代理ip
      deprecated: false
      description: |-
        账号更换代理ip，可实现在线切换。
        也可退出后重新登录传新的代理ip。
      tags:
        - 核心 API 模块/登录模块
        - 基础API/登录模块
      parameters:
        - name: VideosApi-token
          in: header
          description: ''
          required: true
          example: '{{VideosApi-token}}'
          schema:
            type: string
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                appId:
                  type: string
                  description: 设备ID
                  additionalProperties: false
                proxyIp:
                  type: string
                  description: 代理ip
              x-apifox-orders:
                - appId
                - proxyIp
              required:
                - appId
                - proxyIp
            example:
              appId: '{{appid}}'
              proxyIp: socks5://x:x@111.153.185.21:11332
      responses:
        '200':
          description: ''
          content:
            application/json:
              schema:
                type: object
                properties:
                  ret:
                    type: integer
                  msg:
                    type: string
                required:
                  - ret
                  - msg
                x-apifox-orders:
                  - ret
                  - msg
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/登录模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-374343450-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
