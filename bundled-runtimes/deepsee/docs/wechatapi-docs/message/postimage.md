# 发送图片消息

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /message/postImage:
    post:
      summary: 发送图片消息
      deprecated: false
      description: >-
        #### 注意

        发送图片接口会返回cdn相关的信息，如有需求同一张图片发送多次，第二次及以后发送时可使用接口返回的cdn信息拼装xml调用[转发图片接口](http://apifox.videosapi.com/api-170454743)，这样可以缩短发送时间
      tags:
        - 核心 API 模块/消息模块
        - 基础API/消息模块
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
                toWxid:
                  type: string
                  description: 好友/群的ID
                imgUrl:
                  type: string
                  description: 图片链接
              x-apifox-orders:
                - appId
                - toWxid
                - imgUrl
              required:
                - appId
                - toWxid
                - imgUrl
            example:
              appId: '{{appid}}'
              toWxid: '*********@chatroom'
              imgUrl: http://dummyimage.com/400x400
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
                      toWxid:
                        type: string
                        description: 接收人的wxid
                      createTime:
                        type: integer
                        description: 发送时间
                      msgId:
                        type: integer
                        description: 消息ID
                      newMsgId:
                        type: integer
                        description: 消息ID
                      type:
                        type: 'null'
                        description: 消息类型
                      aesKey:
                        type: string
                        description: cdn相关的aeskey
                      fileId:
                        type: string
                        description: cdn相关的fileid
                      length:
                        type: integer
                        description: 图片文件大小
                      width:
                        type: integer
                        description: 图片宽度
                      height:
                        type: integer
                        description: 图片高度
                      md5:
                        type: string
                        description: 图片md5
                    required:
                      - toWxid
                      - createTime
                      - msgId
                      - newMsgId
                      - type
                      - aesKey
                      - fileId
                      - length
                      - width
                      - height
                      - md5
                    x-apifox-orders:
                      - toWxid
                      - createTime
                      - msgId
                      - newMsgId
                      - type
                      - aesKey
                      - fileId
                      - length
                      - width
                      - height
                      - md5
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
                  toWxid: '*********@chatroom'
                  createTime: 0
                  msgId: 640355969
                  newMsgId: 8992614056172360000
                  type: null
                  aesKey: 7678796e6d70626e6b626c6f7375616b
                  fileId: >-
                    3052020100044b30490201000204e49785f102033d11fd0204136166b4020465966eea042437646265323234362d653662662d343464392d39336*********13661363863646266390204052418020201000400
                  length: 1096
                  width: 400
                  height: 400
                  md5: e6355eab0393facbd6a2cde3f990ef60
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/消息模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454734-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
