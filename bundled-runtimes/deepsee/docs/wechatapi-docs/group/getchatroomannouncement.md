# 获取群公告

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /group/getChatroomAnnouncement:
    post:
      summary: 获取群公告
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
                chatroomId:
                  type: string
                  description: 群ID
              x-apifox-orders:
                - appId
                - chatroomId
              required:
                - appId
                - chatroomId
            example:
              appId: '{{appid}}'
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
                  data:
                    type: object
                    properties:
                      announcement:
                        type: string
                        description: 群公告内容
                      announcementEditor:
                        type: string
                        description: 群公告作者的wxid
                      publishTime:
                        type: integer
                        description: 群公告发布时间
                    required:
                      - announcement
                      - announcementEditor
                      - publishTime
                    x-apifox-orders:
                      - announcement
                      - announcementEditor
                      - publishTime
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
                  announcement: 群公告哈
                  announcementEditor: '**********'
                  publishTime: 1703839509
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/群管理接口
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454721-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
