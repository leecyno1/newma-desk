# 同意进群

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /group/agreeJoinRoom:
    post:
      summary: 同意进群
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
                url:
                  type: string
                  description: 邀请进群回调消息中的url
              x-apifox-orders:
                - appId
                - url
              required:
                - appId
                - url
            example:
              appId: '{{appid}}'
              url: >-
                https://support.weixin.qq.com/cgi-bin/mmsupport-bin/addchatroombyinvite?ticket=A%2FtYjg2L%2FGB%2FHYqOwzWNMQ%3D%3D
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
                      chatroomId:
                        type: string
                        description: 群ID
                    required:
                      - chatroomId
                    x-apifox-orders:
                      - chatroomId
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
                  chatroomId: '**********@chatroom'
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/群管理接口
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454723-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
