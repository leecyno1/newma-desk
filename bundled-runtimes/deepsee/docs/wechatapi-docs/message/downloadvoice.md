# 下载语音

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /message/downloadVoice:
    post:
      summary: 下载语音
      deprecated: false
      description: >-
        >
        **语音silk格式转换MP3地址[：silk转mp3](https://github.com/kn007/silk-v3-decoder)**
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
                msgId:
                  type: number
                  description: 回调消息中的msgId
              x-apifox-orders:
                - appId
                - xml
                - msgId
              required:
                - appId
                - msgId
                - xml
            example:
              appId: '{{appid}}'
              msgId: 5332565812
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
                        description: 语音文件链接地址，7天有效
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
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454749-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
