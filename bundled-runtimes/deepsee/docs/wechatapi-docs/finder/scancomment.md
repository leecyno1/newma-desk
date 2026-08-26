# 扫码评论

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /finder/scanComment:
    post:
      summary: 扫码评论
      deprecated: false
      description: ''
      tags:
        - 核心 API 模块/视频号模块
        - 基础API/视频号模块
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
                myUserName:
                  type: string
                  description: 自己的username
                myRoleType:
                  type: integer
                  description: 自己的roletype
                qrContent:
                  type: string
                  description: 获取方式：官方视频号助手->内容管理->视频->复制视频链接
                objectId:
                  type: integer
                  description: 视频号的objectId
                commentContent:
                  type: string
                  description: 评论内容
                replyUsername:
                  type: string
                  description: 回复的username
                refCommentId:
                  type: integer
                  description: 回复评论时传
                rootCommentId:
                  type: integer
                  description: 回复评论时传
              required:
                - appId
                - myUserName
                - myRoleType
                - qrContent
                - objectId
                - commentContent
              x-apifox-orders:
                - appId
                - myUserName
                - myRoleType
                - qrContent
                - objectId
                - commentContent
                - replyUsername
                - refCommentId
                - rootCommentId
            example:
              appId: '{{appid}}'
              useProxy: true
              myUserName: >-
                v2_060000231003b20faec8c7e28811c4d5cc0ded37b0779c48c759a7446a87688c2774e5300c32@finder
              myRoleType: 3
              qrContent: https://weixin.qq.com/sph/ArJBdPlIM
              objectId: 14195037502970006000
              commentContent: hhh
              replyUsername: ''
              refCommentId: 0
              rootCommentId: 0
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
                      commentId:
                        type: integer
                        description: 评论ID
                      clientid:
                        type: string
                    required:
                      - commentId
                      - clientid
                    x-apifox-orders:
                      - commentId
                      - clientid
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
                  commentId: 14311728323297282000
                  clientid: '988946786'
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/视频号模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454811-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
