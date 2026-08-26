# 撤回消息

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /message/revokeMsg:
    post:
      summary: 撤回消息
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
                msgId:
                  type: string
                  description: 发送类接口返回的msgId
                newMsgId:
                  type: string
                  description: 发送类接口返回的newMsgId
                createTime:
                  type: string
                  description: 发送类接口返回的createTime
              x-apifox-orders:
                - appId
                - toWxid
                - msgId
                - newMsgId
                - createTime
              required:
                - appId
                - toWxid
                - msgId
                - newMsgId
                - createTime
            example:
              appId: '{{appid}}'
              toWxid: '***********@chatroom'
              msgId: '769533801'
              newMsgId: '5271007655758710001'
              createTime: '1704163145'
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
      x-apifox-folder: 核心 API 模块/消息模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454747-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
