# 扫码进群

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /group/joinRoomUsingQRCode:
    post:
      summary: 扫码进群
      deprecated: false
      description: qrUrl是通过解析群二维码图片获得的内容
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
                qrUrl:
                  type: string
                  description: 二维码的链接
              x-apifox-orders:
                - appId
                - qrUrl
              required:
                - appId
                - qrUrl
            example:
              appId: '{{appid}}'
              qrUrl: >-
                https://weixin.qq.com/g/AwYAALLELoeKLg-qWAtkYtBdyTg_i2TG22w1GS-cL1GFO9J4AemIyZAw7RSuIpZw
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
                      chatroomName:
                        type: string
                        description: 群名称
                      html:
                        type: 'null'
                      chatroomId:
                        type: string
                        description: 群ID
                    required:
                      - chatroomName
                      - html
                      - chatroomId
                    x-apifox-orders:
                      - chatroomName
                      - html
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
                  chatroomName: VideosApi-test-room(2)
                  html: null
                  chatroomId: '**********@chatroom'
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/群管理接口
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454730-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
