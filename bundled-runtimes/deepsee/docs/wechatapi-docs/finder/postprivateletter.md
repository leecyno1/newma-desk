# 发私信文本消息

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /finder/postPrivateLetter:
    post:
      summary: 发私信文本消息
      deprecated: false
      description: 消息回调接口内返回了msgsessionid可直接使用、或者使用获取私信sessionid接口
      tags:
        - 核心 API 模块/视频号模块
        - 基础API/视频号模块
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
                content:
                  type: string
                  description: 私信内容
                toUserName:
                  type: string
                  description: 接收方的username
                myUserName:
                  type: string
                  description: 自己的usenrame
                msgSessionId:
                  type: string
                  description: 可通过/getMsgSessionId接口获取
              required:
                - appId
                - content
                - msgSessionId
                - myUserName
                - toUserName
              x-apifox-orders:
                - appId
                - content
                - toUserName
                - myUserName
                - msgSessionId
            example:
              appId: '{{appid}}'
              useProxy: true
              content: 文本
              msgSessionId: >-
                3eab1521919d4531c83a166faa56cf844737c4a295b127f3edcb68ed4375d049@findermsg
              myUserName: >-
                v2_060000231003b20faec8c7e28811c4d5cc0ded37b0779c48c759a7446a87688c2774e5300c32@finder
              toUserName: >-
                v2_060000231003b20faec8c6e18f10c7d6c903ec3db0776955d3d97c6b329d6aa58693bcdb7ad1@finder
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
                      newMsgId:
                        type: integer
                    required:
                      - newMsgId
                    x-apifox-orders:
                      - newMsgId
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
                  newMsgId: 243683914400108300
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/视频号模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454784-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
