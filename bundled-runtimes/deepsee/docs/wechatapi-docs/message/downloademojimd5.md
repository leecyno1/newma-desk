# 下载emoji

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /message/downloadEmojiMd5:
    post:
      summary: 下载emoji
      deprecated: false
      description: '> 下载emoji时应强制加上下载后缀.png'
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
                emojiMd5:
                  type: string
                  description: emoji图片的md5
              x-apifox-orders:
                - appId
                - emojiMd5
              required:
                - appId
                - emojiMd5
            example:
              appId: '{{appid}}'
              emojiMd5: sada5996wreFEDE3696sd23r
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
                      url:
                        type: string
                        description: emoji表情链接地址，7天有效
                    required:
                      - url
                    x-apifox-orders:
                      - url
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
                  Url: >-
                    http://videosapi.oos-hbwh.ctyunapi.cn/20250905/wx_Ce9GH6GkpMqsZ8HGWUkQh/21d08948-a109-4efd-ba98-2a297de1e7d0.zip?AWSAccessKeyId=6c1f06ea4941b5a857c0&Expires=1757642892&Signature=yunPCEDD2Pwx3LLwcHy8vK5dbvE%3D
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/消息模块/下载
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454751-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
