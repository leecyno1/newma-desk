# 发送appmsg消息

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /message/postAppMsg:
    post:
      summary: 发送appmsg消息
      deprecated: false
      description: >-
        #### 注意

        本接口可用于发送所有包含<appmsg>节点的消息，例如：音乐分享、视频号、引用消息等等

        引用消息发送需要发送引用消息后观察回调，保存结构。根据回调修改结构的**svrid**（对应需要引用的newmsgid）和**title**(需要发送的消息内容），可群内或者聊天内测试。
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
                appmsg:
                  type: string
                  description: 回调消息中的appmsg节点内容
              x-apifox-orders:
                - appId
                - toWxid
                - appmsg
              required:
                - appId
                - toWxid
                - appmsg
            example:
              appId: '{{appid}}'
              toWxid: '***********@chatroom'
              appmsg: "<appmsg appid=\"\" sdkver=\"0\">\n\t\t<title>一审宣判！蔡鄂生被判死缓</title>\n\t\t<des />\n\t\t<action />\n\t\t<type>5</type>\n\t\t<showtype>0</showtype>\n\t\t<soundtype>0</soundtype>\n\t\t<mediatagname />\n\t\t<messageext />\n\t\t<messageaction />\n\t\t<content />\n\t\t<contentattr>0</contentattr>\n\t\t<url>http://mp.weixin.qq.com/s?__biz=MjM5MjAxNDM4MA==&amp;mid=2666774093&amp;idx=1&amp;sn=aa405094dd00034d004f6e8287f86e9b&amp;chksm=bcc9d903635a9c284591edda1f027c467245d922d7d66c32d3cd2c6af1c969a7ea0896aa7639&amp;scene=0&amp;xtrack=1#rd</url>\n\t\t<lowurl />\n\t\t<dataurl />\n\t\t<lowdataurl />\n\t\t<appattach>\n\t\t\t<totallen>0</totallen>\n\t\t\t<attachid />\n\t\t\t<emoticonmd5 />\n\t\t\t<fileext />\n\t\t\t<cdnthumburl>3057020100044b304902010002048399cc8402032f57ed02041388e6720204658e922d042462666538346165322d303035382d343262322d616538322d3337306231346630323534360204051408030201000405004c53d900</cdnthumburl>\n\t\t\t<cdnthumbmd5>ea3d5e8d4059cb4db0a3c39c789f2d6f</cdnthumbmd5>\n\t\t\t<cdnthumblength>93065</cdnthumblength>\n\t\t\t<cdnthumbwidth>1080</cdnthumbwidth>\n\t\t\t<cdnthumbheight>459</cdnthumbheight>\n\t\t\t<cdnthumbaeskey>849df42ab37c8cadb324fe94ba46d76e</cdnthumbaeskey>\n\t\t\t<aeskey>849df42ab37c8cadb324fe94ba46d76e</aeskey>\n\t\t\t<encryver>0</encryver>\n\t\t</appattach>\n\t\t<extinfo />\n\t\t<sourceusername>gh_363b924965e9</sourceusername>\n\t\t<sourcedisplayname>人民日报</sourcedisplayname>\n\t\t<thumburl>https://mmbiz.qpic.cn/sz_mmbiz_jpg/xrFYciaHL08DCJtwQefqrH8JcohbOHhTpyCPab8IgDibkTv3Pspicjw8TRHnoic2tmiafBtUHg7ObZznpWocwkCib6Tw/640?wxtype=jpeg&amp;wxfrom=0</thumburl>\n\t\t<md5 />\n\t\t<statextstr />\n\t\t<mmreadershare>\n\t\t\t<itemshowtype>0</itemshowtype>\n\t\t</mmreadershare>\n\t</appmsg>"
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
                        type: integer
                        description: 消息类型
                    required:
                      - toWxid
                      - createTime
                      - msgId
                      - newMsgId
                      - type
                    x-apifox-orders:
                      - toWxid
                      - createTime
                      - msgId
                      - newMsgId
                      - type
                required:
                  - ret
                  - msg
                  - data
                x-apifox-orders:
                  - ret
                  - msg
                  - data
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/消息模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454740-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
