# 创建视频号

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /finder/createFinder:
    post:
      summary: 创建视频号
      deprecated: false
      description: ''
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
                nickName:
                  type: string
                  description: 视频号昵称
                headImg:
                  type: string
                  description: 视频号头像链接
                signature:
                  type: string
                  description: 视频号签名
                sex:
                  type: integer
                  description: 性别
              required:
                - appId
                - headImg
                - nickName
              x-apifox-orders:
                - appId
                - nickName
                - headImg
                - signature
                - sex
            example:
              appId: '{{appid}}'
              useProxy: true
              signature: 测试。
              headImg: >-
                https://wx.qlogo.cn/mmhead/ver_1/ZYUmcl1UNzyB2onM08Ij901TaUOLIjHj2UicK3XGDsjEWl4XgQN5IjodunHicBVsZiaZc1iaGCRfluAxkzyibbiau3WBfFj2nprzKp2KryicMjGIvDbWOQGmibwVK648a3o4A8hD/0
              nickName: VideosApi
              sex: 1
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
                      username:
                        type: string
                        description: 视频号username
                      nickname:
                        type: string
                        description: 视频号昵称
                      headUrl:
                        type: string
                        description: 头像
                      signature:
                        type: string
                        description: 简介
                      followFlag:
                        type: integer
                    required:
                      - username
                      - nickname
                      - headUrl
                      - signature
                      - followFlag
                    x-apifox-orders:
                      - username
                      - nickname
                      - headUrl
                      - signature
                      - followFlag
                required:
                  - ret
                  - msg
                  - data
                x-apifox-orders:
                  - ret
                  - msg
                  - data
              examples:
                '1':
                  summary: 成功示例
                  value:
                    ret: 200
                    msg: 操作成功
                    data:
                      username: >-
                        v2_060000231003b20faec8c7e28811c4d50ded37b0779c48c759a7446a87688c2774e5300c32@finder
                      nickname: VideosApi
                      headUrl: >-
                        http://wx.qlogo.cn/finderhead/AbruuZ3ILCkWiallQicn8kbXiafrvbTc6uMOYC7WiaOzmle9GcMavFI3nSdMsAc916JoG9DRWAEHew/0
                      signature: 测试。
                      followFlag: 1
                '2':
                  summary: 异常示例
                  value:
                    ret: 500
                    msg: 创建视频号失败
                    data:
                      code: '-4002'
                      msg: 名字已被使用，请修改后再试。
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/视频号模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454786-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
