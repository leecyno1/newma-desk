# 发送小程序消息

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /message/postMiniApp:
    post:
      summary: 发送小程序消息
      deprecated: false
      description: ''
      tags:
        - 核心 API 模块/消息模块
        - 基础API/消息模块
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
                toWxid:
                  type: string
                  description: 好友/群的ID
                miniAppId:
                  type: string
                  description: 小程序ID
                displayName:
                  type: string
                  description: 小程序名称
                pagePath:
                  type: string
                  description: 小程序打开的地址
                coverImgUrl:
                  type: string
                  description: 小程序封面图链接
                title:
                  type: string
                  description: 小程序标题
                userName:
                  type: string
                  description: 归属的用户ID
              x-apifox-orders:
                - appId
                - toWxid
                - miniAppId
                - displayName
                - pagePath
                - coverImgUrl
                - title
                - userName
              required:
                - appId
                - toWxid
                - miniAppId
                - userName
                - title
                - coverImgUrl
                - pagePath
                - displayName
            example:
              appId: '{{appid}}'
              toWxid: '***********@chatroom'
              miniAppId: wx1f9ea355b47256dd
              userName: gh_690acf47ea05@app
              title: 最快29分钟 好吃水果送到家
              coverImgUrl: >-
                https://che-static.vzhimeng.com/img/2023/10/30/67d55942-e43c-4fdb-8396-506794ddbdbc.jpg
              pagePath: pages/homeDelivery/index.html
              displayName: 百果园+
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
                      toWxid:
                        type: string
                        description: 接收人的wxid
                      createTime:
                        type: integer
                        description: 发送时间
                      msgId:
                        type: integer
                        description: 消息ID
                      newMsgId:
                        type: integer
                        description: 消息ID
                      type:
                        type: integer
                        description: 消息类型
                    required:
                      - toWxid
                      - createTime
                      - msgId
                      - newMsgId
                      - type
                    x-apifox-orders:
                      - toWxid
                      - createTime
                      - msgId
                      - newMsgId
                      - type
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
                  toWxid: '***********@chatroom'
                  createTime: 1704162674
                  msgId: 769533691
                  newMsgId: 3190424380344821000
                  type: 33
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/消息模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454741-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
