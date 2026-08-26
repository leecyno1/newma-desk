# 添加群成员为好友

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /group/addGroupMemberAsFriend:
    post:
      summary: 添加群成员为好友
      deprecated: false
      description: 添加群成员为好友，若对方关闭从群聊添加的权限则添加失败
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
                chatroomId:
                  type: string
                  description: 群ID
                memberWxid:
                  type: string
                  description: 群成员的wxid
                content:
                  type: string
                  description: 加好友的招呼语
              x-apifox-orders:
                - appId
                - chatroomId
                - memberWxid
                - content
              required:
                - appId
                - chatroomId
                - content
                - memberWxid
            example:
              appId: '{{appid}}'
              chatroomId: '**********@chatroom'
              content: hallo
              memberWxid: wxid_**********
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
                      v3:
                        type: string
                        description: 添加群成员的v3，通过好友后会通过回调消息返回此值
                    required:
                      - v3
                    x-apifox-orders:
                      - v3
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
                  v3: >-
                    v3_020b3826fd030100000000003a070e7757675c000000501ea9a3dba12f95f6b60a0536a1adb690dcccc9bf58cc80765e6eb16bffa5996420bb**********bdcd5689df8dfb21d40af93d286f72c3a0e8cfa6dcb68afed39226f008c6@stranger
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/群管理接口
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454724-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
