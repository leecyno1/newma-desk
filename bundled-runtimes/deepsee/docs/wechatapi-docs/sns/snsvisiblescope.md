# 设置朋友圈可见范围

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /sns/snsVisibleScope:
    post:
      summary: 设置朋友圈可见范围
      deprecated: false
      description: |-
        #### 朋友圈可见范围 option 可选项
        - 1:全部
        - 2:最近半年
        - 3:最近一个月
        - 4:最近三天
      tags:
        - 核心 API 模块/朋友圈模块
        - 基础API/朋友圈模块
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
                option:
                  type: number
                  description: 朋友圈可见范围
              x-apifox-orders:
                - appId
                - option
              required:
                - appId
                - option
            example:
              appId: '{{appid}}'
              option: 3
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
              example:
                ret: 200
                msg: 操作成功
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/朋友圈模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454755-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
