# 转发图片

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /message/forwardImage:
    post:
      summary: 转发图片
      deprecated: false
      description: >-
        #### 注意

        若通过发送图片消息获取cdn信息后可替换xml中的aeskey、cdnthumbaeskey、cdnthumburl、cdnmidimgurl、length、md5等参数来进行转发
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
                xml:
                  type: string
                  description: 文件消息的xml
              x-apifox-orders:
                - appId
                - toWxid
                - xml
              required:
                - appId
                - toWxid
                - xml
            example:
              appId: '{{appid}}'
              toWxid: '***********@chatroom'
              xml: "<?xml version=\"1.0\"?>\n<msg>\n\t<img aeskey=\"294774c8ac2ca8f8114e4d58d2ba78a5\" encryver=\"1\" cdnthumbaeskey=\"294774c8ac2ca8f8114e4d58d2ba78a5\" cdnthumburl=\"3057020100044b304902010002043904752002032f7d6d02046bb5bade020465937656042436626431373937632d613430642d346137662d626230352d3832613335353935333130630204051818020201000405004c543d00\" cdnthumblength=\"2253\" cdnthumbheight=\"120\" cdnthumbwidth=\"111\" cdnmidheight=\"0\" cdnmidwidth=\"0\" cdnhdheight=\"0\" cdnhdwidth=\"0\" cdnmidimgurl=\"3057020100044b304902010002043904752002032f7d6d02046bb5bade020465937656042436626431373937632d613430642d346137662d626230352d3832613335353935333130630204051818020201000405004c543d00\" length=\"4061\" md5=\"799ee4beed51720525232aef6a0d2ec4\" />\n\t<platform_signature></platform_signature>\n\t<imgdatahash></imgdatahash>\n</msg>"
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
                  toWxid: '***********@chatroom'
                  createTime: 0
                  msgId: 769533749
                  newMsgId: 7003061792458481000
                  type: null
                  aesKey: 294774c8ac2ca8f8114e4d58d2ba78a5
                  fileId: >-
                    3057020100044b304902010002043904752002032f7d6d02046bb5bade020465937656042436626431373937632d613430642d346137662d626230352d3832613335353935333130630204051818020201000405004c543d00
                  length: null
                  width: null
                  height: null
                  md5: null
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/消息模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454743-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
