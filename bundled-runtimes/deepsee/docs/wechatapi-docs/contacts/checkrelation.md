# 检测好友关系

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /contacts/checkRelation:
    post:
      summary: 检测好友关系
      deprecated: true
      description: ''
      tags:
        - 核心 API 模块/联系人相关接口
        - 基础API/联系人模块
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
                wxids:
                  type: array
                  items:
                    type: string
                    description: 好友的wxid
                  description: 好友的wxid
                  minItems: 1
                  maxItems: 20
              x-apifox-orders:
                - appId
                - wxids
              required:
                - appId
                - wxids
            example: |-
              //单个好友
              {
                  "appId": "{{appid}}",
                  "wxids": [
                      "wechatapi"
                  ]
              }
              //多个好友
              {
                  "appId": "{{appid}}",
                  "wxids": [
                      "ier****isi",
                      "kit****622",
                      "F10****0104",
                      "leo****001",
                      "kel****0428",
                      "wxi****612",
                      "wxi****522"
                  ]
              }
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
                    type: array
                    items:
                      type: object
                      properties:
                        wxid:
                          type: string
                          description: 好友的wxid
                        relation:
                          type: integer
                          description: 0:正常 1:删除 2:被拉黑3:已拉黑对方4:功能异常5:检测频繁6:未知状态7:未知错误99:其他
                      x-apifox-orders:
                        - wxid
                        - relation
                      required:
                        - wxid
                        - relation
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
                msg: 检测好友关系成功
                data:
                  - wxid: wxid_adfwh232asd
                    relation: 1
                  - wxid: wxid_adfgsfghe2322
                    relation: 2
                  - wxid: wxid_adfgsfgfnytj2
                    relation: 0
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/联系人相关接口
      x-apifox-status: obsolete
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454706-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
