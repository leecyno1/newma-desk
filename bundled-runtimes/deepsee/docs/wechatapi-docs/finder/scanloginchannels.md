# 扫码登录视频号助手

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /finder/scanLoginChannels:
    post:
      summary: 扫码登录视频号助手
      deprecated: false
      description: >-
        username**为空则默认登录管理员身份**，

        username填写运营者视频号ID则登录运营者身份。

        如需登录其他运营者的身份的，调用[获取运营者信息接口](https://post.wechatapi.net/finder/getfinderinfo)获取运营者身份的username
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
                qrContent:
                  type: string
                  description: 视频号助手官方二维码解析出来的内容
                username:
                  type: string
                  description: 登录的视频号ID
              required:
                - appId
                - qrContent
                - username
              x-apifox-orders:
                - appId
                - qrContent
                - username
            example:
              appId: '{{appid}}'
              useProxy: true
              qrContent: https://channels****pcFfmmHUNA_RzmLg
              username: v2_060000231003*********d1@finder
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
                      sessionId:
                        type: string
                      finderList:
                        type: array
                        items:
                          type: object
                          properties:
                            finderUsername:
                              type: string
                            nickname:
                              type: string
                            headImgUrl:
                              type: string
                            coverImgUrl:
                              type: string
                            spamFlag:
                              type: integer
                            acctType:
                              type: integer
                            authIconType:
                              type: integer
                            ownerWxUin:
                              type: integer
                            adminNickname:
                              type: string
                            categoryFlag:
                              type: string
                            uniqId:
                              type: string
                            isMasterFinder:
                              type: boolean
                          x-apifox-orders:
                            - finderUsername
                            - nickname
                            - headImgUrl
                            - coverImgUrl
                            - spamFlag
                            - acctType
                            - authIconType
                            - ownerWxUin
                            - adminNickname
                            - categoryFlag
                            - uniqId
                            - isMasterFinder
                      acctStatus:
                        type: integer
                    required:
                      - finderList
                      - sessionId
                      - acctStatus
                    x-apifox-orders:
                      - sessionId
                      - finderList
                      - acctStatus
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
      x-apifox-folder: 核心 API 模块/视频号模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454790-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
