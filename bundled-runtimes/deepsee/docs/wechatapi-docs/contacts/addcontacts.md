# 添加好友/同意好友

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /contacts/addContacts:
    post:
      summary: 添加好友/同意好友
      deprecated: false
      description: |-
        本接口建议在线3天后再进行调用。
        好友添加成功后，会通过回调消息推送一条包含v3的消息，可用于判断好友是否添加成功。
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
                scene:
                  type: integer
                  description: |-
                    添加来源，同意添加好友时传回调消息xml中的scene值。
                    添加好友时的枚举值如下：
                    3 ：微信号搜索
                    4 ：QQ好友
                    8 ：来自群聊
                    15：手机号
                option:
                  type: integer
                  description: 操作类型，2添加好友 3同意好友 4拒绝好友
                v3:
                  type: string
                  description: 通过搜索或回调消息获取到的v3
                v4:
                  type: string
                  description: 通过搜索或回调消息获取到的v4
                content:
                  type: string
                  description: 添加好友时的招呼语
              x-apifox-orders:
                - appId
                - scene
                - option
                - v3
                - v4
                - content
              required:
                - appId
                - scene
                - content
                - v4
                - v3
                - option
            example:
              appId: '{appid}'
              scene: 3
              content: hallo
              v4: v4_000b708f0***862304d4799758ba@stranger
              v3: v3_020b3826f***3d28d39226f008c6@stranger
              option: 2
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
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/联系人相关接口
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454701-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
