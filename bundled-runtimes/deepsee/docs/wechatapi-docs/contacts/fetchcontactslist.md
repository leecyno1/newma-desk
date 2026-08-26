# 获取通讯录列表(包含群聊)

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /contacts/fetchContactsList:
    post:
      summary: 获取通讯录列表(包含群聊)
      deprecated: false
      description: >-
        本接口为长耗时接口，耗时时间根据好友数量递增，若接口超时可通过[获取通讯录列表缓存接口](https://post.wechatapi.net/contacts/fetchcontactslistcache)获取响应结果


        **注意：<font color='red'>本接口返回的群聊仅为保存到通讯录中的群聊</font>**

        **此接口未返回的群聊，当有人在群内发言时，会有回调消息推送到对应的appid，拿到群id后可通过[获取群信息接口](https://post.wechatapi.net/group/getchatroominfo)拿到此群的信息做后续处理**
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
              x-apifox-orders:
                - appId
              required:
                - appId
            example:
              appId: '{appid}'
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
                      friends:
                        type: array
                        items:
                          type: string
                        description: 好友的wxid
                      chatrooms:
                        type: array
                        items:
                          type: string
                        description: 保存到通讯录中群聊的ID
                      ghs:
                        type: array
                        items:
                          type: string
                        description: 关注的公众号ID
                    required:
                      - friends
                      - chatrooms
                      - ghs
                    x-apifox-orders:
                      - friends
                      - chatrooms
                      - ghs
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
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454698-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
