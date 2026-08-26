# 获取所有运营者身份

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /finder/getFinderInfo:
    post:
      summary: 获取所有运营者身份
      deprecated: false
      description: >-
        本接口与扫码登录视频号助手配合使用，如需登录其他运营者的身份，需要先用本接口获取所有视频号身份的username，使用[扫码登录视频号助手接口登录](https://post.wechatapi.net/finder/scanloginchannels)
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
              required:
                - appId
              x-apifox-orders:
                - appId
            example:
              appId: '{{appid}}'
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
                      finderUsername:
                        type: string
                        description: 视频号ID
                      nickname:
                        type: string
                        description: 视频号名称
                      headImgUrl:
                        type: string
                        description: 头像链接
                      acctType:
                        type: string
                        description: 身份 1 管理员 2 运营者
                      ownerWxUin:
                        type: string
                    required:
                      - finderUsername
                      - nickname
                      - headImgUrl
                      - acctType
                      - ownerWxUin
                    x-apifox-orders:
                      - finderUsername
                      - headImgUrl
                      - nickname
                      - acctType
                      - ownerWxUin
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
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-384294068-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
