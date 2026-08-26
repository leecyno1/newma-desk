# 发送链接消息

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /message/postLink:
    post:
      summary: 发送链接消息
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
                title:
                  type: string
                  description: 链接标题
                desc:
                  type: string
                  description: 链接描述
                linkUrl:
                  type: string
                  description: 链接地址
                thumbUrl:
                  type: string
                  description: 链接缩略图地址
              x-apifox-orders:
                - appId
                - toWxid
                - title
                - desc
                - linkUrl
                - thumbUrl
              required:
                - appId
                - toWxid
                - title
                - desc
                - linkUrl
                - thumbUrl
            example:
              appId: '{{appid}}'
              toWxid: '**********@chatroom'
              title: 澳门这一夜
              desc: 39岁郭碧婷用珠圆玉润的身材，狠狠打脸了白幼瘦女星
              linkUrl: >-
                https://mbd.baidu.com/newspage/data/landingsuper?context=%7B%22nid%22%3A%22news_8864265500294006781%22%7D&n_type=-1&p_from=-1
              thumbUrl: >-
                https://pics3.baidu.com/feed/0824ab18972bd407a9403f336648d15c0db30943.jpeg@f_auto?token=d26f7f142871542956aaa13799ba1946
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
                  toWxid: '*********@chatroom'
                  createTime: 1703841982
                  msgId: 769523572
                  newMsgId: 3358797740318931000
                  type: 5
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/消息模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454737-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
