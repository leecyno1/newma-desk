# 设置好友仅聊天

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /contacts/setFriendPermissions:
    post:
      summary: 设置好友仅聊天
      deprecated: false
      description: 设置完好友仅聊天后若发现手机展示不是设置的结果，可能是手机缓存未刷新，重新进入页面刷新查看
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
                wxid:
                  type: string
                  description: 好友的wxid
                onlyChat:
                  type: boolean
                  description: 设置好友是否仅聊天
              x-apifox-orders:
                - appId
                - wxid
                - onlyChat
              required:
                - appId
                - wxid
                - onlyChat
            example:
              appId: '{{appid}}'
              wxid: wxid_**********
              onlyChat: true
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
                msg: 设置好友权限成功
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/联系人相关接口
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454705-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
