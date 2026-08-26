# 标签列表

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /label/list:
    post:
      summary: 标签列表
      deprecated: false
      description: ''
      tags:
        - 核心 API 模块/标签模块
        - 基础API/标签模块
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
                    type: object
                    properties:
                      labelList:
                        type: array
                        items:
                          type: object
                          properties:
                            labelName:
                              type: string
                              description: 标签名称
                            labelId:
                              type: integer
                              description: 标签ID
                          x-apifox-orders:
                            - labelName
                            - labelId
                    required:
                      - labelList
                    x-apifox-orders:
                      - labelList
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
                data:
                  labelList:
                    - labelName: 朋友
                      labelId: 1
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/标签模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454772-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
