# 删除群成员

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /group/removeMember:
    post:
      summary: 删除群成员
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
                  description: 删除的群成员wxid，多个英文逗号分隔
                chatroomId:
                  type: string
                  description: 群ID
              x-apifox-orders:
                - appId
                - wxids
                - chatroomId
              required:
                - appId
                - wxids
                - chatroomId
            example:
              appId: '{{appid}}'
              wxids: wxid_**********
              chatroomId: '**********@chatroom'
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
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454715-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
