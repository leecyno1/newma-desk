# 转发视频

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /message/forwardVideo:
    post:
      summary: 转发视频
      deprecated: false
      description: >-
        #### 注意

        若通过发送视频消息获取cdn信息后可替换xml中的aeskey、cdnthumbaeskey、cdnvideourl、cdnthumburl、length等参数来进行转发
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
              xml: "<?xml version=\"1.0\"?>\n<msg>\n\t<videomsg aeskey=\"5c5163d06757faae44eacc2146ba0575\" cdnvideourl=\"3057020100044b304902010002043904752002032f7d6d02046bb5bade0204659376a6042465623261663836382d336363332d346131332d383037642d3464626162316638303634360204051800040201000405004c56f900\" cdnthumbaeskey=\"5c5163d06757faae44eacc2146ba0575\" cdnthumburl=\"3057020100044b304902010002043904752002032f7d6d02046bb5bade0204659376a6042465623261663836382d336363332d346131332d383037642d3464626162316638303634360204051800040201000405004c56f900\" length=\"490566\" playlength=\"7\" cdnthumblength=\"8192\" cdnthumbwidth=\"135\" cdnthumbheight=\"240\" fromusername=\"zhangchuan2288\" md5=\"8804c121e9db91dd844f7a34035beb88\" newmd5=\"\" isplaceholder=\"0\" rawmd5=\"\" rawlength=\"0\" cdnrawvideourl=\"\" cdnrawvideoaeskey=\"\" overwritenewmsgid=\"0\" originsourcemd5=\"\" isad=\"0\" />\n</msg>"
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
                        type: 'null'
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
                        description: 视频文件大小
                    required:
                      - toWxid
                      - createTime
                      - msgId
                      - newMsgId
                      - type
                      - aesKey
                      - fileId
                      - length
                    x-apifox-orders:
                      - toWxid
                      - createTime
                      - msgId
                      - newMsgId
                      - type
                      - aesKey
                      - fileId
                      - length
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
                  createTime: null
                  msgId: 769533762
                  newMsgId: 2099537549112929300
                  type: null
                  aesKey: 5c5163d06757faae44eacc2146ba0575
                  fileId: null
                  length: 490566
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/消息模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454744-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
