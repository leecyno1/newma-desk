# 获取群成员列表

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /group/getChatroomMemberList:
    post:
      summary: 获取群成员列表
      deprecated: false
      description: ''
      tags:
        - 核心 API 模块/群管理接口
        - 基础API/群模块
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
                chatroomId:
                  type: string
                  description: 群ID
              x-apifox-orders:
                - appId
                - chatroomId
              required:
                - appId
                - chatroomId
            example:
              appId: '{{appid}}'
              chatroomId: '**********@chatroom'
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
                      memberList:
                        type: array
                        items:
                          type: object
                          properties:
                            wxid:
                              type: string
                              description: 群成员的wxid
                            nickName:
                              type: string
                              description: 群成员昵称
                            inviterUserName:
                              type: string
                              description: 邀请人的wxid
                              nullable: true
                            memberFlag:
                              type: integer
                              description: 标识
                            displayName:
                              type: string
                              description: 在本群内的昵称
                              nullable: true
                            bigHeadImgUrl:
                              type: string
                              description: 大尺寸头像
                            smallHeadImgUrl:
                              type: string
                              description: 小尺寸头像
                          required:
                            - wxid
                            - nickName
                            - inviterUserName
                            - memberFlag
                            - displayName
                            - bigHeadImgUrl
                            - smallHeadImgUrl
                          x-apifox-orders:
                            - wxid
                            - nickName
                            - inviterUserName
                            - memberFlag
                            - displayName
                            - bigHeadImgUrl
                            - smallHeadImgUrl
                        description: 群成员列表
                      chatroomOwner:
                        type: 'null'
                        description: 群主的wxid
                      adminWxid:
                        type: 'null'
                        description: 管理的wxid
                    required:
                      - memberList
                      - chatroomOwner
                      - adminWxid
                    x-apifox-orders:
                      - memberList
                      - chatroomOwner
                      - adminWxid
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
                  memberList:
                    - wxid: VideosAPi
                      nickName: VIdeosAPi
                      inviterUserName: null
                      memberFlag: 1
                      displayName: null
                      bigHeadImgUrl: >-
                        https://wx.qlogo.cn/mmhead/ver_1/T0MtLBu618rUlZqaAiaWfucmVibiawiciaSibPfz11siaLZr0qSxQTAR9lu7YicDwYAHNia1je79icxul6bzQ4LLZopiaM9EdYAEublPCLV29QKLv26ictBHjWsWnE0lvYGjibB9DkE6q/0
                      smallHeadImgUrl: >-
                        https://wx.qlogo.cn/mmhead/ver_1/T0MtLBu618rUlZqaAiaWfucmVibiawiciaSibPfz11siaLZr0qSxQTAR9lu7YicDwYAHNia1je79icxul6bzQ4LLZopiaM9EdYAEublPCLV29QKLv26ictBHjWsWnE0lvYGjibB9DkE6q/132
                    - wxid: wxid_**********
                      nickName: Ashley
                      inviterUserName: VideosApi
                      memberFlag: 1
                      displayName: null
                      bigHeadImgUrl: >-
                        https://wx.qlogo.cn/mmhead/ver_1/5ibSibfNKwpv0TLLuSFv2hibEBqShib4BKsaxHZ2v10y9F93ibO5lK4bwib47qtuwsLZD8HY7fVicibWlWvehCLDCdicy38NaIbVupuMZMDwiaXozjUhk/0
                      smallHeadImgUrl: >-
                        https://wx.qlogo.cn/mmhead/ver_1/5ibSibfNKwpv0TLLuSFv2hibEBqShib4BKsaxHZ2v10y9F93ibO5lK4bwib47qtuwsLZD8HY7fVicibWlWvehCLDCdicy38NaIbVupuMZMDwiaXozjUhk/132
                    - wxid: wxid_**********
                      nickName: G
                      inviterUserName: VideosAPi
                      memberFlag: 2049
                      displayName: G1
                      bigHeadImgUrl: >-
                        https://wx.qlogo.cn/mmhead/ver_1/FMkteDauMN35F3lhfavibDYpGibfHqrsMICtqBbWDfwfQOnIYfgHBpOJLLbac0Wf3odowXcePFHMzj954EeFOiaKcsgIaMedw5KWZhBpaLsFfSK5HNAE7AQODQ1FfrPiaTCh/0
                      smallHeadImgUrl: >-
                        https://wx.qlogo.cn/mmhead/ver_1/FMkteDauMN35F3lhfavibDYpGibfHqrsMICtqBbWDfwfQOnIYfgHBpOJLLbac0Wf3odowXcePFHMzj954EeFOiaKcsgIaMedw5KWZhBpaLsFfSK5HNAE7AQODQ1FfrPiaTCh/132
                  chatroomOwner: VideosAPi
                  adminWxid:
                    - wxid_**********
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/群管理接口
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454719-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
