# 发送语音消息

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /message/postVoice:
    post:
      summary: 发送语音消息
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
                voiceUrl:
                  type: string
                  description: 语音文件的链接，仅支持silk格式
                voiceDuration:
                  type: integer
                  description: 语音时长，单位毫秒
              x-apifox-orders:
                - appId
                - toWxid
                - voiceUrl
                - voiceDuration
              required:
                - appId
                - toWxid
                - voiceUrl
                - voiceDuration
            example:
              appId: '{{appid}}'
              toWxid: '*********@chatroom'
              voiceUrl: >-
                https://scrm-1308498490.cos.ap-shanghai.myqcloud.com/pkg/response.silk?q-sign-algorithm=sha1&q-ak=AKIDmOkqfDUUDfqjMincBSSAbleGaeQv96mB&q-sign-time=1703841529;1703848729&q-key-time=1703841529;1703848729&q-header-list=&q-url-param-list=&q-signature=781831fe71ad4bbb582715bf197a9cf86ec80c97
              voiceDuration: 2000
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
                  toWxid: '*********@chatroom'
                  createTime: 1704357563
                  msgId: 640355967
                  newMsgId: 2321462558768366600
                  type: null
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/消息模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454735-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
