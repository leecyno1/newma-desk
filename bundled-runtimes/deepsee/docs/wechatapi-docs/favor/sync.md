# 同步收藏夹

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /favor/sync:
    post:
      summary: 同步收藏夹
      deprecated: false
      description: |
        #### 注意:
        响应结果中会包含已删除的的收藏夹记录，通过flag=1来判断已删除
      tags:
        - 核心 API 模块/收藏夹模块
        - 基础API/收藏夹模块
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
                syncKey:
                  type: string
                  description: 翻页key，首次传空，获取下一页传接口返回的syncKey
              x-apifox-orders:
                - appId
                - syncKey
              required:
                - appId
            example:
              appId: '{{appid}}'
              syncKey: ''
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
                      syncKey:
                        type: string
                        description: 翻页key
                      list:
                        type: array
                        items:
                          type: object
                          properties:
                            favId:
                              type: integer
                              description: 收藏夹ID
                            type:
                              type: integer
                              description: 收藏内容类型
                            flag:
                              type: integer
                              description: 收藏夹标识
                            updateTime:
                              type: integer
                              description: 收藏时间
                          required:
                            - favId
                            - type
                            - flag
                            - updateTime
                          x-apifox-orders:
                            - favId
                            - type
                            - flag
                            - updateTime
                    required:
                      - syncKey
                      - list
                    x-apifox-orders:
                      - syncKey
                      - list
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
                  syncKey: CAESCAgBEJyi9e4C
                  list:
                    - favId: 2
                      type: 1
                      flag: 1
                      updateTime: 1448465918
                    - favId: 1
                      type: 2
                      flag: 1
                      updateTime: 1448465922
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/收藏夹模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454780-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
