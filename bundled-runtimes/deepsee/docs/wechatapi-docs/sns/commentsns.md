# 评论/删除评论

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /sns/commentSns:
    post:
      summary: 评论/删除评论
      deprecated: false
      description: >-
        在新设备登录后的1-3天内，您将无法使用朋友圈发布、点赞、评论等功能。在此期间，如果尝试进行这些操作，您将收到来自微信团队的提醒。请注意遵守相关规定。
      tags:
        - 核心 API 模块/朋友圈模块
        - 基础API/朋友圈模块
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
                snsId:
                  type: number
                  description: 朋友圈ID
                operType:
                  type: integer
                  description: 1评论 2删除评论
                wxid:
                  type: string
                  description: 评论的好友wxid
                commentId:
                  type: string
                  description: 回复某条评论或删除某条评论
                content:
                  type: string
                  description: 评论内容
              x-apifox-orders:
                - appId
                - snsId
                - operType
                - wxid
                - commentId
                - content
              required:
                - appId
                - snsId
                - operType
                - wxid
            example:
              appId: '{{appid}}'
              snsId: 14287710653886042000
              operType: 2
              wxid: wxid_***********
              commentId: 1
              content: ''
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
      x-apifox-folder: 核心 API 模块/朋友圈模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454769-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
