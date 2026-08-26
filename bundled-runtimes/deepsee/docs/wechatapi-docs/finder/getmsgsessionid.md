# 获取私信SessionId

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /finder/getMsgSessionId:
    post:
      summary: 获取私信SessionId
      deprecated: false
      description: 消息回调接口内返回可不用调用此接口。如未返回需调用本接口。
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
                toUserName:
                  type: string
                  description: 对方的username
                myUserName:
                  type: string
                  description: 自己的username
                myAccountType:
                  type: integer
                  description: 身份类型 1:视频号身份  2:微信号身份
              required:
                - appId
                - toUserName
                - myAccountType
                - myUserName
              x-apifox-orders:
                - appId
                - toUserName
                - myUserName
                - myAccountType
            example:
              appId: '{{appid}}'
              useProxy: true
              toUserName: >-
                v2_060000231003b20faec8c6e18f10c7d6c903ec3db0776955d3d97c6b329d6aa58693bcdb7ad1@finder
              myAccountType: 2
              myUserName: ''
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
                      toUsername:
                        type: string
                      sessionId:
                        type: string
                      rejectMsg:
                        type: integer
                      enableAction:
                        type: integer
                      msgExtInfo:
                        type: string
                    required:
                      - toUsername
                      - sessionId
                      - rejectMsg
                      - enableAction
                      - msgExtInfo
                    x-apifox-orders:
                      - toUsername
                      - sessionId
                      - rejectMsg
                      - enableAction
                      - msgExtInfo
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
                  toUsername: >-
                    v2_060000231003b20faec8c6e18f10c7d6c903ec3db0776955d3d97c6b329d6aa58693bcdb7ad1@finder
                  sessionId: >-
                    3eab1521919d4531c83a166faa56cf844737c4a295b127f3edcb68ed4375d049@findermsg
                  rejectMsg: 0
                  enableAction: 1
                  msgExtInfo: CAIQAw==
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/视频号模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454789-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
