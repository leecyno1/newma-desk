# 管理员操作

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /group/adminOperate:
    post:
      summary: 管理员操作
      deprecated: false
      description: 添加、删除群管理员，转让群主
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
                operType:
                  type: integer
                  description: 操作类型  1：添加群管理（可添加多个微信号） 2：删除群管理（可删除多个） 3：转让（只能转让一个微信号）
                wxids:
                  type: array
                  items:
                    type: string
                    description: 群管理的wxid
              x-apifox-orders:
                - appId
                - chatroomId
                - operType
                - wxids
              required:
                - appId
                - chatroomId
                - operType
                - wxids
            example:
              appId: '{{appid}}'
              chatroomId: '**********@chatroom'
              operType: 1
              wxids:
                - wxid_**********
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
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454727-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
