# 邀请/添加 进群

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /group/inviteMember:
    post:
      summary: 邀请/添加 进群
      deprecated: false
      description: ''
      tags:
        - 核心 API 模块/群管理接口
        - 基础API/群模块
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
                  type: string
                  description: 邀请进群的好友wxid，多个英文逗号分隔
                chatroomId:
                  type: string
                  description: 群ID
                reason:
                  type: string
                  description: 邀请进群的说明
              x-apifox-orders:
                - appId
                - wxids
                - chatroomId
                - reason
              required:
                - appId
                - wxids
                - chatroomId
                - reason
            example:
              appId: '{{appid}}'
              wxids: wxid_**********
              chatroomId: '**********@chatroom'
              reason: ''
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
      x-apifox-folder: 核心 API 模块/群管理接口
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454714-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
