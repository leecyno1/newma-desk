# 获取群信息

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /group/getChatroomInfo:
    post:
      summary: 获取群信息
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
                  description: 群ID（通过“获取通讯录列表”接口返回）
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
                      chatroomId:
                        type: string
                        description: 群ID
                      nickName:
                        type: string
                        description: 群名称
                      pyInitial:
                        type: string
                        description: 群名称的拼音首字母
                      quanPin:
                        type: string
                        description: 群名称的全拼
                      sex:
                        type: integer
                      remark:
                        type: string
                        description: 群备注，仅自己可见
                      remarkPyInitial:
                        type: string
                        description: 群备注的拼音首字母
                      remarkQuanPin:
                        type: string
                        description: 群备注的全拼
                      chatRoomNotify:
                        type: integer
                        description: 群消息是否提醒
                      chatRoomOwner:
                        type: string
                        description: 群主的wxid
                      smallHeadImgUrl:
                        type: string
                        description: 群头像链接
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
                              description: 群成员的昵称
                            inviterUserName:
                              type: string
                              description: 邀请人的wxid
                              nullable: true
                            memberFlag:
                              type: integer
                              description: 标识
                            displayName:
                              type: 'null'
                              description: 在本群内的昵称
                            bigHeadImgUrl:
                              type: 'null'
                              description: 大尺寸头像
                            smallHeadImgUrl:
                              type: 'null'
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
                    required:
                      - chatroomId
                      - nickName
                      - pyInitial
                      - quanPin
                      - sex
                      - remark
                      - remarkPyInitial
                      - remarkQuanPin
                      - chatRoomNotify
                      - chatRoomOwner
                      - smallHeadImgUrl
                      - memberList
                    x-apifox-orders:
                      - chatroomId
                      - nickName
                      - pyInitial
                      - quanPin
                      - sex
                      - remark
                      - remarkPyInitial
                      - remarkQuanPin
                      - chatRoomNotify
                      - chatRoomOwner
                      - smallHeadImgUrl
                      - memberList
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
                  chatroomId: VideosApi@chatroom
                  nickName: VideosApi test
                  pyInitial: VideosApiTEST
                  quanPin: VideosApitest
                  sex: 0
                  remark: VideosApi test private
                  remarkPyInitial: VideosApiTEST
                  remarkQuanPin: VideosApiTEST
                  chatRoomNotify: 1
                  chatRoomOwner: VideosAPi
                  smallHeadImgUrl: >-
                    https://wx.qlogo.cn/mmcrhead/PiajxSqBRaEJEIII6n6NUHudK1r**********PRoWm7Km3ZQIpq8xp65nD6yUm8BHxzqhV1ic1jQvvnv/0
                  memberList:
                    - wxid: VideosAPi
                      nickName: VideosAPi
                      inviterUserName: null
                      memberFlag: 1
                      displayName: null
                      bigHeadImgUrl: null
                      smallHeadImgUrl: null
                    - wxid: wxid_***********
                      nickName: Ashley
                      inviterUserName: VideosAPi
                      memberFlag: 1
                      displayName: null
                      bigHeadImgUrl: null
                      smallHeadImgUrl: null
                    - wxid: wxid_*********
                      nickName: G
                      inviterUserName: VideosAPi
                      memberFlag: 1
                      displayName: null
                      bigHeadImgUrl: null
                      smallHeadImgUrl: null
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/群管理接口
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454718-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
