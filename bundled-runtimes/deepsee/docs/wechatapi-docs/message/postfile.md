# 发送文件消息

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /message/postFile:
    post:
      summary: 发送文件消息
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
                fileUrl:
                  type: string
                  description: 文件链接
                fileName:
                  type: string
                  description: 文件名
              x-apifox-orders:
                - appId
                - toWxid
                - fileUrl
                - fileName
              required:
                - appId
                - toWxid
                - fileName
                - fileUrl
            example:
              appId: '{{appid}}'
              toWxid: '***********@chatroom'
              fileName: a909.xls
              fileUrl: >-
                https://scrm-1308498490.cos.ap-shanghai.myqcloud.com/pkg/a909-99066ce80e03.xls?q-sign-algorithm=sha1&q-ak=AKIDmOkqfDUUDfqjMincBSSAbleGaeQv96mB&q-sign-time=1703841209;1703848409&q-key-time=1703841209;1703848409&q-header-list=&q-url-param-list=&q-signature=2a60b0f8d9169550cd83c4a3ca9cd18138b4bb88
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
                  createTime: 1703841225
                  msgId: 769523509
                  newMsgId: 4399037329770756000
                  type: 6
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/消息模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454733-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
