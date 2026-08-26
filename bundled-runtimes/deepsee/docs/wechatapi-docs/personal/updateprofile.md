# 修改个人信息

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /personal/updateProfile:
    post:
      summary: 修改个人信息
      deprecated: false
      description: |
        **注意** 修改个人信息需要单独设置每一项
        比如修改昵称则参数仅传appId和nickName
        修改地区则参数可传appId、country、province、city
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
                city:
                  type: string
                  description: 城市
                country:
                  type: string
                  description: 国家
                nickName:
                  type: string
                  description: 昵称
                province:
                  type: string
                  description: 省份
                sex:
                  type: string
                  description: 性别 1:男 2:女
                signature:
                  type: string
                  description: 签名
              x-apifox-orders:
                - appId
                - city
                - country
                - nickName
                - province
                - sex
                - signature
              required:
                - appId
                - country
                - nickName
                - signature
                - sex
                - province
            example:
              appId: '{{appid}}'
              useProxy: true
              city: ''
              country: ''
              nickName: ''
              province: ''
              sex: 1
              signature: ......
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
      x-apifox-folder: 核心 API 模块/个人模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454778-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
