# 同步企微好友

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /im/sync:
    post:
      summary: 同步企微好友
      deprecated: false
      description: ''
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
              x-apifox-orders:
                - appId
              required:
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
                      remark:
                        type: string
                        description: 备注
                      userName:
                        type: string
                        description: 企业微信号
                      nickName:
                        type: string
                        description: 企业微信名称
                      bigHeadImg:
                        type: string
                        description: 大头像
                      smallHeadImg:
                        type: string
                        description: 小头像
                      appId:
                        type: string
                        description: 企业微信APPID
                      descWordingId:
                        type: string
                        description: 企业ID
                    x-apifox-orders:
                      - userName
                      - nickName
                      - remark
                      - bigHeadImg
                      - smallHeadImg
                      - appId
                      - descWordingId
                    required:
                      - userName
                      - nickName
                      - remark
                      - bigHeadImg
                      - smallHeadImg
                      - appId
                      - descWordingId
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
                  - userName: 259**nim
                    nickName: '**'
                    remark: ''
                    bigHeadImg: http://wew**qpoCghewE/
                    smallHeadImg: http://**sapevHrU/
                    appId: 23**00
                    descWordingId: RwpR**KOP
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/联系人相关接口
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-176184392-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
