# 修改头像

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /personal/updateHeadImg:
    post:
      summary: 修改头像
      deprecated: false
      description: '**注意** 修改头像后需要将手机的微信进程关掉，然后重启查看最新头像'
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
                headImgUrl:
                  type: string
                  description: 头像的图片地址
              x-apifox-orders:
                - appId
                - headImgUrl
              required:
                - appId
            example:
              appId: '{{appid}}'
              useProxy: true
              headImgUrl: >-
                https://wx.qlogo.cn/mmhead/ver_1/REoLX7KfdibFAgDbtoeXGNjE6sGa8NCib8UaiazlekKjuLneCvicM4xQpuEbZWjjQooSicsKEbKdhqCOCpTHWtnBqdJicJ0I3CgZumwJ6SxR3ibuNs/0
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
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454779-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
