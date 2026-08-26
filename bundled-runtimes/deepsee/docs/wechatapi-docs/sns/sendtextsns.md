# 发送文字朋友圈

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /sns/sendTextSns:
    post:
      summary: 发送文字朋友圈
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
                allowWxIds:
                  type: array
                  items:
                    type: string
                    description: 好友的wxid
                  description: 允许谁看
                atWxIds:
                  type: array
                  items:
                    type: string
                    description: 好友的wxid
                  description: 提醒谁看
                disableWxIds:
                  type: array
                  items:
                    type: string
                    description: 好友的wxid
                  description: 不给谁看
                privacy:
                  type: boolean
                  description: 是否私密
                  default: 'false'
                content:
                  type: string
                  description: 朋友圈文字内容
              x-apifox-orders:
                - appId
                - allowWxIds
                - atWxIds
                - disableWxIds
                - privacy
                - content
              required:
                - appId
                - content
            example:
              appId: '{{appid}}'
              useProxy: true
              allowWxIds: []
              atWxIds: []
              disableWxIds: []
              content: test
              privacy: false
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
                      id:
                        type: integer
                        description: 朋友圈ID
                      userName:
                        type: string
                        description: 朋友圈作者的wxid
                      nickName:
                        type: string
                        description: 朋友圈作者的昵称
                      createTime:
                        type: integer
                        description: 发布时间
                    required:
                      - id
                      - userName
                      - nickName
                      - createTime
                    x-apifox-orders:
                      - id
                      - userName
                      - nickName
                      - createTime
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
                  id: 14287800629617234000
                  userName: VideosAPi
                  nickName: VideosAPi
                  createTime: 1703238562
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/朋友圈模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454759-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
