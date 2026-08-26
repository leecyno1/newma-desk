# 下载图片

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /message/downloadImage:
    post:
      summary: 下载图片
      deprecated: false
      description: '**注意** 如果下载图片失败，可尝试下载另外两种图片类型，并非所有图片都会有高清、常规图片'
      tags:
        - 核心 API 模块/消息模块/下载
        - 基础API/消息模块/下载
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
                xml:
                  type: string
                  description: 回调消息中的XML
                type:
                  type: integer
                  description: 下载的图片类型 1:高清图片  2:常规图片  3:缩略图
                  default: 2
              x-apifox-orders:
                - appId
                - xml
                - type
              required:
                - appId
                - type
                - xml
            example:
              appId: '{{appid}}'
              type: 2
              xml: |-
                <?xml version="1**********
                </msg>
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
                      fileUrl:
                        type: string
                        description: 图片链接地址，7天有效
                    required:
                      - fileUrl
                    x-apifox-orders:
                      - fileUrl
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
                  fileUrl: >-
                    http://videosapi.oos-hbwh.ctyunapi.cn/20250905/wx_Ce9GH6GkpMqsZ8HGWUkQh/21ires=1757642892&Signature=yunPCEDD2Pwx3LLwcHy8vK5dbvE%3D
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/消息模块/下载
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454748-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
