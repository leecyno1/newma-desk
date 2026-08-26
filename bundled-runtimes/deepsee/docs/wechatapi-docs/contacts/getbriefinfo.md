# 获取群/好友简要信息

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /contacts/getBriefInfo:
    post:
      summary: 获取群/好友简要信息
      deprecated: false
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
                    description: 好友的wxid1
                  description: 好友/群的wxid
                  minItems: 1
                  maxItems: 20
              x-apifox-orders:
                - appId
                - wxids
              required:
                - appId
                - wxids
            example: |-
              //单个好友/群
              {
                  "appId": "{{appid}}",
                  "wxids": [
                      "wechatapi"
                  ]
              }
              //多个好友/群
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
                        userName:
                          type: string
                        nickName:
                          type: string
                        pyInitial:
                          type: string
                        quanPin:
                          type: string
                        sex:
                          type: integer
                        remark:
                          type: string
                        remarkPyInitial:
                          type: string
                        remarkQuanPin:
                          type: string
                        signature:
                          type: 'null'
                        alias:
                          type: string
                        snsBgImg:
                          type: 'null'
                        country:
                          type: string
                        bigHeadImgUrl:
                          type: string
                        smallHeadImgUrl:
                          type: string
                        description:
                          type: 'null'
                        cardImgUrl:
                          type: 'null'
                        labelList:
                          type: string
                        province:
                          type: string
                        city:
                          type: string
                        phoneNumList:
                          type: 'null'
                      x-apifox-orders:
                        - userName
                        - nickName
                        - pyInitial
                        - quanPin
                        - sex
                        - remark
                        - remarkPyInitial
                        - remarkQuanPin
                        - signature
                        - alias
                        - snsBgImg
                        - country
                        - bigHeadImgUrl
                        - smallHeadImgUrl
                        - description
                        - cardImgUrl
                        - labelList
                        - province
                        - city
                        - phoneNumList
                required:
                  - ret
                  - msg
                  - data
                x-apifox-orders:
                  - ret
                  - msg
                  - data
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/联系人相关接口
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454703-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
