# 获取设备记录

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /personal/getSafetyInfo:
    post:
      summary: 获取设备记录
      deprecated: false
      description: ''
      tags:
        - 核心 API 模块/个人模块
        - 基础API/个人模块
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
              x-apifox-orders:
                - appId
              required:
                - appId
            example:
              appId: '{{appid}}'
              proxyIp: ''
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
                      list:
                        type: array
                        items:
                          type: object
                          properties:
                            uuid:
                              type: string
                              description: 设备ID
                            deviceName:
                              type: string
                              description: 设备名称
                            deviceType:
                              type: string
                              description: 设备类型
                            lastTime:
                              type: integer
                              description: 最后操作时间
                          required:
                            - uuid
                            - deviceName
                            - deviceType
                            - lastTime
                          x-apifox-orders:
                            - uuid
                            - deviceName
                            - deviceType
                            - lastTime
                        description: 设备记录
                    required:
                      - list
                    x-apifox-orders:
                      - list
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
                  list:
                    - uuid: 087b139951b776e0416b5015d0b98109
                      deviceName: iPhone 13 Pro
                      deviceType: iPhone iOS17.2
                      lastTime: 1703218815
                    - uuid: f7e4bda161f7a6a7361ca62141cded23
                      deviceName: 张传的MacBook Pro
                      deviceType: iMac MacBookPro17,1 OSX OSX 13.3.1 build(22E261)
                      lastTime: 1703206819
                    - uuid: 80d6218be93f570a971d8c605fa542c3
                      deviceName: iPad
                      deviceType: iPad iOS14.5.1
                      lastTime: 1703065642
                    - uuid: 197e97585d02c9cd6e6de68c74c81780
                      deviceName: iPad
                      deviceType: iPad iOS14.5.1
                      lastTime: 1701300706
                    - uuid: bf5eb4d8498f4affac1cbfb8aa936d2a
                      deviceName: iPad
                      deviceType: iPad iPadOS14.3
                      lastTime: 1696729849
                    - uuid: 33ac7f39ed3d7115d9c15f07981a264a
                      deviceName: iPad
                      deviceType: iPad iPadOS14.5.1
                      lastTime: 1695050733
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/个人模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454776-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
