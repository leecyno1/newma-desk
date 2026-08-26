# 修改群备注

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /group/modifyChatroomRemark:
    post:
      summary: 修改群备注
      deprecated: false
      description: |-
        群备注仅自己可见
        修改完群备注后若发现手机未展示修改后的备注，可能是手机缓存未刷新，手机聊天框多切换几次会刷新。
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
                chatroomRemark:
                  type: string
                  description: 群备注
                chatroomId:
                  type: string
                  description: 群ID
              x-apifox-orders:
                - appId
                - chatroomRemark
                - chatroomId
              required:
                - appId
                - chatroomRemark
                - chatroomId
            example:
              appId: '{{appid}}'
              chatroomRemark: VideosApi test private
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
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454712-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
