# 隐私设置

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /personal/privacySettings:
    post:
      summary: 隐私设置
      deprecated: false
      description: |-
        **option 说明**
        - 4: 加我为朋友时需要验证
        - 7: 向我推荐通讯录朋友
        - 8: 添加我的方式 手机号
        - 25: 添加我的方式 微信号
        - 38: 添加我的方式 群聊
        - 39: 添加我的方式 我的二维码
        - 40: 添加我的方式 名片
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
                option:
                  type: integer
                  description: |-
                    隐私设置的选项
                         4: 加我为朋友时需要验证
                         7: 向我推荐通讯录朋友
                         8: 添加我的方式 手机号
                         25: 添加我的方式 微信号
                         38: 添加我的方式 群聊
                         39: 添加我的方式 我的二维码
                         40: 添加我的方式 名片
                open:
                  type: boolean
                  description: 开关
              x-apifox-orders:
                - appId
                - option
                - open
              required:
                - appId
                - open
            example:
              appId: '{{appid}}'
              useProxy: true
              open: true
              option: 4
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
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454777-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
