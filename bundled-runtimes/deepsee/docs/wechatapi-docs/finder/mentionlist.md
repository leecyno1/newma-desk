# 获取消息列表

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /finder/mentionList:
    post:
      summary: 获取消息列表
      deprecated: false
      description: '> **首次执行返回为空，拿返回的lastBuff传参即可获取数据。**'
      tags:
        - 核心 API 模块/视频号模块
        - 基础API/视频号模块
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
                myUserName:
                  type: string
                  description: 自己的username
                myRoleType:
                  type: integer
                  description: 自己的roletype，默认为3
                reqScene:
                  type: integer
                  description: 消息类型 3是点赞 4是评论 5是关注
                lastBuff:
                  type: string
                  description: 首次传空，后续传接口返回的lastBuffer
              required:
                - appId
                - myUserName
                - myRoleType
                - reqScene
              x-apifox-orders:
                - appId
                - myUserName
                - myRoleType
                - lastBuff
                - reqScene
            example:
              appId: '{{appid}}'
              useProxy: true
              myUserName: >-
                v2_060000231003b20faec8c7e28811c4d5cc0ded37b0779c48c759a7446a87688c2774e5300c32@finder
              lastBuff: ''
              myRoleType: 3
              reqScene: 3
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
                      list:
                        type: object
                        properties:
                          mentions:
                            type: array
                            items:
                              type: object
                              properties:
                                headUrl:
                                  type: string
                                  description: 头像
                                nickname:
                                  type: string
                                  description: 昵称
                                mentionType:
                                  type: integer
                                  description: 消息类型
                                mentionContent:
                                  type: string
                                  description: 消息内容
                                createtime:
                                  type: integer
                                  description: 时间
                                thumbUrl:
                                  type: string
                                  description: 缩略图
                                mentionId:
                                  type: integer
                                  description: 消息ID
                                refObjectId:
                                  type: integer
                                  description: 引用作品ID
                                refCommentId:
                                  type: integer
                                  description: 引用评论ID
                                flag:
                                  type: integer
                                extflag:
                                  type: integer
                                refContent:
                                  type: string
                                mediaType:
                                  type: integer
                                description:
                                  type: string
                                replyNickname:
                                  type: string
                                refObjectNonceId:
                                  type: string
                                username:
                                  type: string
                                  description: 对方的username、微信ID
                                contact:
                                  type: object
                                  properties:
                                    contact:
                                      type: object
                                      properties:
                                        username:
                                          type: string
                                          description: username
                                        nickname:
                                          type: string
                                          description: 昵称
                                        headUrl:
                                          type: string
                                          description: 头像
                                        seq:
                                          type: integer
                                        signature:
                                          type: string
                                          description: 简介
                                        authInfo:
                                          type: object
                                          properties: {}
                                          x-apifox-orders: []
                                        coverImgUrl:
                                          type: string
                                        spamStatus:
                                          type: integer
                                        extFlag:
                                          type: integer
                                        extInfo:
                                          type: object
                                          properties:
                                            country:
                                              type: string
                                              description: 国家
                                            province:
                                              type: string
                                              description: 省份
                                            city:
                                              type: string
                                              description: 城市
                                            sex:
                                              type: integer
                                              description: 性别
                                          required:
                                            - country
                                            - province
                                            - city
                                            - sex
                                          x-apifox-orders:
                                            - country
                                            - province
                                            - city
                                            - sex
                                          description: 拓展信息
                                        liveStatus:
                                          type: integer
                                        liveCoverImgUrl:
                                          type: string
                                        liveInfo:
                                          type: object
                                          properties:
                                            anchorStatusFlag:
                                              type: integer
                                            switchFlag:
                                              type: integer
                                            lotterySetting:
                                              type: object
                                              properties:
                                                settingFlag:
                                                  type: integer
                                                attendType:
                                                  type: integer
                                              required:
                                                - settingFlag
                                                - attendType
                                              x-apifox-orders:
                                                - settingFlag
                                                - attendType
                                          required:
                                            - anchorStatusFlag
                                            - switchFlag
                                            - lotterySetting
                                          x-apifox-orders:
                                            - anchorStatusFlag
                                            - switchFlag
                                            - lotterySetting
                                        status:
                                          type: integer
                                      required:
                                        - username
                                        - nickname
                                        - headUrl
                                        - seq
                                        - signature
                                        - authInfo
                                        - coverImgUrl
                                        - spamStatus
                                        - extFlag
                                        - extInfo
                                        - liveStatus
                                        - liveCoverImgUrl
                                        - liveInfo
                                        - status
                                      x-apifox-orders:
                                        - username
                                        - nickname
                                        - headUrl
                                        - seq
                                        - signature
                                        - authInfo
                                        - coverImgUrl
                                        - spamStatus
                                        - extFlag
                                        - extInfo
                                        - liveStatus
                                        - liveCoverImgUrl
                                        - liveInfo
                                        - status
                                  required:
                                    - contact
                                  x-apifox-orders:
                                    - contact
                                refObjectType:
                                  type: integer
                                extInfo:
                                  type: object
                                  properties:
                                    appName:
                                      type: string
                                    entityId:
                                      type: string
                                  required:
                                    - appName
                                    - entityId
                                  x-apifox-orders:
                                    - appName
                                    - entityId
                                svrMentionId:
                                  type: integer
                                followFlag:
                                  type: integer
                                orderCount:
                                  type: integer
                                interactionCount:
                                  type: integer
                                forceUseRefContent:
                                  type: integer
                              x-apifox-orders:
                                - headUrl
                                - nickname
                                - mentionType
                                - mentionContent
                                - createtime
                                - thumbUrl
                                - mentionId
                                - refObjectId
                                - refCommentId
                                - flag
                                - extflag
                                - refContent
                                - mediaType
                                - description
                                - replyNickname
                                - refObjectNonceId
                                - username
                                - contact
                                - refObjectType
                                - extInfo
                                - svrMentionId
                                - followFlag
                                - orderCount
                                - interactionCount
                                - forceUseRefContent
                        required:
                          - mentions
                        x-apifox-orders:
                          - mentions
                      lastBuff:
                        type: string
                        description: 翻页表示，对应入参
                    required:
                      - list
                      - lastBuff
                    x-apifox-orders:
                      - list
                      - lastBuff
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
                  list:
                    mentions:
                      - headUrl: >-
                          http://wx.qlogo.cn/finderhead/ajNVdqHZLLBn2wux0rkD6gc4NLsC0zqSeWeJNnp1bGnnPCHl0tt56A/0
                        nickname: 我的生活选择
                        mentionType: 18
                        mentionContent: 谢谢你的关注
                        createtime: 1699863094
                        thumbUrl: ''
                        mentionId: 268435463
                        refObjectId: 140674547237424
                        refCommentId: 0
                        flag: 0
                        extflag: 3
                        refContent: ''
                        mediaType: 0
                        description: ''
                        replyNickname: ''
                        refObjectNonceId: ''
                        username: >-
                          v2_060000231003b20faec8c7e58d1dcad6ce0ced33b0773abe5958d674168d77f7102844347047@finder
                        contact:
                          contact:
                            username: >-
                              v2_060000231003b20faec8c7e58d1dcad6ce0ced33b0773abe5958d674168d77f7102844347047@finder
                            nickname: 我的生活选择
                            headUrl: >-
                              https://wx.qlogo.cn/finderhead/ver_1/qOI5dkUOJ8YodCzzxP9ibztL9XrEbTeq0qJSXXeWribxs0eJicNBHOOLtJOAKpltTyboILgerib13g2tbQfws6QFiajvcvKD935KeibMcVYeguegA/0
                            seq: 57
                            signature: 追求自己想要的生活，努力前进，让自己变的更好
                            authInfo: {}
                            coverImgUrl: ''
                            spamStatus: 0
                            extFlag: 262156
                            extInfo:
                              country: CN
                              province: Hunan
                              city: Shaoyang
                              sex: 2
                            liveStatus: 2
                            liveCoverImgUrl: ''
                            liveInfo:
                              anchorStatusFlag: 2048
                              switchFlag: 53727
                              lotterySetting:
                                settingFlag: 0
                                attendType: 4
                            status: 0
                        refObjectType: 0
                        extInfo:
                          appName: ''
                          entityId: ''
                        svrMentionId: 8
                        followFlag: 0
                        orderCount: 0
                        interactionCount: 0
                        forceUseRefContent: 0
                  lastBuff: CAgQABj///9/
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/视频号模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454804-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
