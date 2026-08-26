# 转发链接

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /message/forwardUrl:
    post:
      summary: 转发链接
      deprecated: false
      description: ''
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
              xml: "<?xml version=\"1.0\"?>\n<msg>\n\t<appmsg appid=\"\" sdkver=\"0\">\n\t\t<title>“李在明遇袭，颈部出血”</title>\n\t\t<des />\n\t\t<action />\n\t\t<type>5</type>\n\t\t<showtype>0</showtype>\n\t\t<soundtype>0</soundtype>\n\t\t<mediatagname />\n\t\t<messageext />\n\t\t<messageaction />\n\t\t<content />\n\t\t<contentattr>0</contentattr>\n\t\t<url>http://mp.weixin.qq.com/s?__biz=MjM5MzI5NTU3MQ==&amp;mid=2652294920&amp;idx=1&amp;sn=ad415f5d83e1471b845b2cb3fca7c3ce&amp;chksm=bce58367ee6ae84b711255705422d1554ee96b92d75648751316639d4aa09289d7827ff1cc85&amp;scene=0&amp;xtrack=1#rd</url>\n\t\t<lowurl />\n\t\t<dataurl />\n\t\t<lowdataurl />\n\t\t<appattach>\n\t\t\t<totallen>0</totallen>\n\t\t\t<attachid />\n\t\t\t<emoticonmd5 />\n\t\t\t<fileext />\n\t\t\t<cdnthumburl>3057020100044b304902010002048399cc8402032f7d6d020468b5bade0204659376ec042463663234636366642d323736612d343533342d623734342d3864623065633235636135390204051808030201000405004c56f900</cdnthumburl>\n\t\t\t<cdnthumbmd5>8e32cafa882f9b4f7c51fb568c0c4f8e</cdnthumbmd5>\n\t\t\t<cdnthumblength>38637</cdnthumblength>\n\t\t\t<cdnthumbwidth>658</cdnthumbwidth>\n\t\t\t<cdnthumbheight>280</cdnthumbheight>\n\t\t\t<cdnthumbaeskey>accc71cbe8ff795a94583fc514d198a8</cdnthumbaeskey>\n\t\t\t<aeskey>accc71cbe8ff795a94583fc514d198a8</aeskey>\n\t\t\t<encryver>0</encryver>\n\t\t</appattach>\n\t\t<extinfo />\n\t\t<sourceusername>gh_d29e0d22a6f9</sourceusername>\n\t\t<sourcedisplayname>澎湃新闻</sourcedisplayname>\n\t\t<thumburl>https://mmbiz.qpic.cn/mmbiz_jpg/yl6JkZAE3SibWvw5icQJpv87X084SRJOVeS3k7KMscRzov1nwicjMYzicyBIpRdJchWKTGPf4eN2H07Jicl11zMK2Pw/640?wxtype=jpeg&amp;wxfrom=0</thumburl>\n\t\t<md5 />\n\t\t<statextstr />\n\t\t<mmreadershare>\n\t\t\t<itemshowtype>0</itemshowtype>\n\t\t</mmreadershare>\n\t</appmsg>\n\t<fromusername>zhangchuan2288</fromusername>\n\t<scene>0</scene>\n\t<appinfo>\n\t\t<version>1</version>\n\t\t<appname></appname>\n\t</appinfo>\n\t<commenturl></commenturl>\n</msg>"
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
              example:
                ret: 200
                msg: 操作成功
                data:
                  toWxid: '***********@chatroom'
                  createTime: 1704163083
                  msgId: 769533781
                  newMsgId: 1947412320722133800
                  type: 5
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/消息模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454745-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
