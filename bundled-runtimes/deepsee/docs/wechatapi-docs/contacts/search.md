# 搜索好友

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /contacts/search:
    post:
      summary: 搜索好友
      deprecated: false
      description: |-
        搜索的联系人信息若已经是好友，响应结果的v3则为好友的wxid
        本接口返回的数据可通过[添加联系人接口](http://apifox.videosapi.com/api-170454701)发送添加好友请求
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
                contactsInfo:
                  type: string
                  description: 搜索的联系人信息，微信号、手机号...
              x-apifox-orders:
                - appId
                - contactsInfo
              required:
                - appId
                - contactsInfo
            example:
              appId: '{appid}'
              contactsInfo: superwechatapi
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
                      v3:
                        type: string
                        description: 搜索好友的v3，添加好友时使用
                      nickName:
                        type: string
                        description: 搜索好友的昵称
                      sex:
                        type: integer
                        description: 搜索好友的性别
                      signature:
                        type: 'null'
                        description: 搜索好友的签名
                      bigHeadImgUrl:
                        type: string
                        description: 搜索好友的大尺寸头像
                      smallHeadImgUrl:
                        type: string
                        description: 搜索好友的小尺寸头像
                      v4:
                        type: string
                        description: 搜索好友的v4，添加好友时使用
                    required:
                      - v3
                      - nickName
                      - sex
                      - signature
                      - bigHeadImgUrl
                      - smallHeadImgUrl
                      - v4
                    x-apifox-orders:
                      - v3
                      - nickName
                      - sex
                      - signature
                      - bigHeadImgUrl
                      - smallHeadImgUrl
                      - v4
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
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454700-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
