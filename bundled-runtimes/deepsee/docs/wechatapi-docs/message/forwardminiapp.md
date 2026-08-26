# 转发小程序

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /message/forwardMiniApp:
    post:
      summary: 转发小程序
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
                coverImgUrl:
                  type: string
                  description: 小程序封面图链接
              x-apifox-orders:
                - appId
                - toWxid
                - xml
                - coverImgUrl
              required:
                - appId
                - toWxid
                - xml
                - coverImgUrl
            example:
              appId: '{{appid}}'
              toWxid: '***********@chatroom'
              xml: "<?xml version=\"1.0\"?>\n<msg>\n\t<appmsg appid=\"\" sdkver=\"0\">\n\t\t<title>👇晒出新年第一杯，点赞赢饮茶月卡</title>\n\t\t<des />\n\t\t<action />\n\t\t<type>33</type>\n\t\t<showtype>0</showtype>\n\t\t<soundtype>0</soundtype>\n\t\t<mediatagname />\n\t\t<messageext />\n\t\t<messageaction />\n\t\t<content />\n\t\t<contentattr>0</contentattr>\n\t\t<url>https://mp.weixin.qq.com/mp/waerrpage?appid=wxafec6f8422cb357b&amp;type=upgrade&amp;upgradetype=3#wechat_redirect</url>\n\t\t<lowurl />\n\t\t<dataurl />\n\t\t<lowdataurl />\n\t\t<appattach>\n\t\t\t<totallen>0</totallen>\n\t\t\t<attachid />\n\t\t\t<emoticonmd5 />\n\t\t\t<fileext />\n\t\t\t<cdnthumburl>3057020100044b30490201000204573515c902032f7d6d020416b7bade020465922a53042437383139393934652d323662652d346430662d396466362d3466303137346139616362390204051408030201000405004c53d900</cdnthumburl>\n\t\t\t<cdnthumbmd5>33cf0a1101e7f8cd3057cd417a691f0b</cdnthumbmd5>\n\t\t\t<cdnthumblength>96673</cdnthumblength>\n\t\t\t<cdnthumbwidth>600</cdnthumbwidth>\n\t\t\t<cdnthumbheight>500</cdnthumbheight>\n\t\t\t<cdnthumbaeskey>6f3098f2ee8b351b6cc9b1818d580356</cdnthumbaeskey>\n\t\t\t<aeskey>6f3098f2ee8b351b6cc9b1818d580356</aeskey>\n\t\t\t<encryver>0</encryver>\n\t\t</appattach>\n\t\t<extinfo />\n\t\t<sourceusername>gh_e9d25e745aae@app</sourceusername>\n\t\t<sourcedisplayname>霸王茶姬</sourcedisplayname>\n\t\t<thumburl />\n\t\t<md5 />\n\t\t<statextstr />\n\t\t<weappinfo>\n\t\t\t<username><![CDATA[gh_e9d25e745aae@app]]></username>\n\t\t\t<appid><![CDATA[wxafec6f8422cb357b]]></appid>\n\t\t\t<type>2</type>\n\t\t\t<version>193</version>\n\t\t\t<weappiconurl><![CDATA[]]></weappiconurl>\n\t\t\t<pagepath><![CDATA[/pages/page/page.html?code=JKD6DA55_3&channelCode=scrm_t664sgg5mrzxkqa]]></pagepath>\n\t\t\t<shareId><![CDATA[0_wxafec6f8422cb357b_25984983017778987@openim_1704162955_0]]></shareId>\n\t\t\t<pkginfo>\n\t\t\t\t<type>0</type>\n\t\t\t\t<md5><![CDATA[]]></md5>\n\t\t\t</pkginfo>\n\t\t\t<appservicetype>0</appservicetype>\n\t\t</weappinfo>\n\t</appmsg>\n\t<fromusername>zhangchuan2288</fromusername>\n\t<scene>0</scene>\n\t<appinfo>\n\t\t<version>1</version>\n\t\t<appname></appname>\n\t</appinfo>\n\t<commenturl></commenturl>\n</msg>"
              coverImgUrl: http://dummyimage.com/400x400
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
                  createTime: 1704163145
                  msgId: 769533801
                  newMsgId: 5271007655758710000
                  type: 33
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/消息模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454746-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
