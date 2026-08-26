# 修改视频号资料

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /finder/updateProfile:
    post:
      summary: 修改视频号资料
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
                  description: 昵称
                headImg:
                  type: string
                  description: 头像链接
                signature:
                  type: string
                  description: 签名
                sex:
                  type: integer
                  description: 性别
                country:
                  type: string
                  description: 国家
                province:
                  type: string
                  description: 省份
                city:
                  type: string
                  description: 城市
                myUserName:
                  type: string
                  description: 自己的username，可通过获取视频号信息接口获取
                myRoleType:
                  type: integer
                  description: 自己的roletype，可通过获取视频号信息接口获取
              required:
                - appId
                - myRoleType
                - myUserName
              x-apifox-orders:
                - appId
                - nickName
                - headImg
                - signature
                - sex
                - country
                - province
                - city
                - myUserName
                - myRoleType
            example:
              appId: '{{appid}}'
              useProxy: true
              signature: 理智，清醒，知进退。
              headImg: >-
                https://wx.qlogo.cn/mmhead/ver_1/ZYUmcl1UNzyB2onM08Ij901TaUOLIjHj2UicK3XGDsjEWl4XgQN5IjodunHicBVsZiaZc1iaGCRfluAxkzyibbiau3WBfFj2nprzKp2KryicMjGIvDbWOQGmibwVK648a3o4A8hD/0
              nickName: 未来可期啊哈
              sex: 1
              city: Nanjing
              province: Jiangsu
              country: CN
              myRoleType: 3
              myUserName: >-
                v2_060000231003b20faec8c7e28811c4d5cc0ded37b0779c48c759a7446a87688c2774e5300c32@finder
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
              examples:
                '1':
                  summary: 成功示例
                  value:
                    ret: 200
                    msg: 操作成功
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
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454800-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
