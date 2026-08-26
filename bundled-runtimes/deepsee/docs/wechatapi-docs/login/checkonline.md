# 检查是否在线

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /login/checkOnline:
    post:
      summary: 检查是否在线
      deprecated: false
      description: 响应结果的data=true则是在线，反之为离线
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
              x-apifox-orders:
                - appId
              required:
                - appId
            example:
              appId: '{{appid}}'
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
                  data:
                    type: boolean
                required:
                  - ret
                  - msg
                  - data
                x-apifox-orders:
                  - ret
                  - msg
                  - data
              example:
                ret: 200
                msg: 操作成功
                data: true
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/登录模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454697-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
