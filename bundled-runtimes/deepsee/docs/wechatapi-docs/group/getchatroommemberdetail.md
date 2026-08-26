# 获取群成员详情

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /group/getChatroomMemberDetail:
    post:
      summary: 获取群成员详情
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
                memberWxids:
                  type: array
                  items:
                    type: string
                    description: 群成员的wxid
              x-apifox-orders:
                - appId
                - chatroomId
                - memberWxids
              required:
                - appId
                - chatroomId
                - memberWxids
            example:
              appId: '{{appid}}'
              chatroomId: '**********@chatroom'
              memberWxids:
                - wxid_**********
                - wxid_**********
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
                    type: array
                    items:
                      type: object
                      properties:
                        userName:
                          type: string
                          description: 群成员的wxid
                        nickName:
                          type: string
                          description: 群成员的昵称
                        pyInitial:
                          type: string
                          description: 群成员昵称的拼音首字母
                        quanPin:
                          type: string
                          description: 群成员昵称的全拼
                        sex:
                          type: integer
                          description: 性别
                        remark:
                          type: string
                          description: 备注
                          nullable: true
                        remarkPyInitial:
                          type: string
                          description: 备注的拼音首字母
                          nullable: true
                        remarkQuanPin:
                          type: string
                          description: 备注的全拼
                          nullable: true
                        chatRoomNotify:
                          type: integer
                          description: 消息通知
                        signature:
                          type: string
                          description: 签名
                          nullable: true
                        alias:
                          type: string
                          description: 微信号
                          nullable: true
                        snsBgImg:
                          type: string
                          description: 朋友圈背景图链接
                        bigHeadImgUrl:
                          type: string
                          description: 大尺寸头像
                        smallHeadImgUrl:
                          type: string
                          description: 小尺寸头像
                        description:
                          type: 'null'
                          description: 描述
                        cardImgUrl:
                          type: 'null'
                          description: 描述的图片链接
                        labelList:
                          type: string
                          description: 标签列表，多个英文逗号分隔
                          nullable: true
                        country:
                          type: string
                          description: 国家
                        province:
                          type: string
                          description: 省份
                          nullable: true
                        city:
                          type: string
                          description: 城市
                          nullable: true
                        phoneNumList:
                          type: array
                          items:
                            type: string
                          description: 手机号码
                        friendUserName:
                          type: string
                          description: 好友的wxid
                        inviterUserName:
                          type: string
                          description: 邀请人的wxid
                          nullable: true
                        memberFlag:
                          type: integer
                          description: 标识
                          nullable: true
                      required:
                        - userName
                        - nickName
                        - pyInitial
                        - quanPin
                        - sex
                        - remark
                        - remarkPyInitial
                        - remarkQuanPin
                        - chatRoomNotify
                        - signature
                        - alias
                        - snsBgImg
                        - bigHeadImgUrl
                        - smallHeadImgUrl
                        - description
                        - cardImgUrl
                        - labelList
                        - country
                        - province
                        - city
                        - phoneNumList
                        - friendUserName
                        - inviterUserName
                        - memberFlag
                      x-apifox-orders:
                        - userName
                        - nickName
                        - pyInitial
                        - quanPin
                        - sex
                        - remark
                        - remarkPyInitial
                        - remarkQuanPin
                        - chatRoomNotify
                        - signature
                        - alias
                        - snsBgImg
                        - bigHeadImgUrl
                        - smallHeadImgUrl
                        - description
                        - cardImgUrl
                        - labelList
                        - country
                        - province
                        - city
                        - phoneNumList
                        - friendUserName
                        - inviterUserName
                        - memberFlag
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
                  - userName: wxid_**********
                    nickName: G
                    pyInitial: G
                    quanPin: G
                    sex: 0
                    remark: null
                    remarkPyInitial: null
                    remarkQuanPin: null
                    chatRoomNotify: 0
                    signature: null
                    alias: null
                    snsBgImg: >-
                      http://shmmsns.qpic.cn/mmsns/s5BUfupeMYsJx3WHf6RyTxAqLUpGZPsgD9l68D5iaf7qibkcjz08RwNwDxj9ToFvnaicFD2X8CtPe4/0
                    bigHeadImgUrl: >-
                      https://wx.qlogo.cn/mmhead/ver_1/tmlG7SpZJMJEh0dA14icl4CWnliaI8pKvVicEMaowRywgVpljBK3nmBib0jHG4eVo5hiaqS7Gg0p7GwCuHopGYqdNBu9WVtxMB8icSFGUjibCDPoGXicPic1r3gx3PQ4YMf3GPfXj/0
                    smallHeadImgUrl: >-
                      https://wx.qlogo.cn/mmhead/ver_1/tmlG7SpZJMJEh0dA14icl4CWnliaI8pKvVicEMaowRywgVpljBK3nmBib0jHG4eVo5hiaqS7Gg0p7GwCuHopGYqdNBu9WVtxMB8icSFGUjibCDPoGXicPic1r3gx3PQ4YMf3GPfXj/132
                    description: null
                    cardImgUrl: null
                    labelList: null
                    country: CN
                    province: Guangdong
                    city: Foshan
                    phoneNumList: null
                    friendUserName: wxid_**********
                    inviterUserName: VideosAPi
                    memberFlag: 0
                  - userName: wxid_**********
                    nickName: Ashley
                    pyInitial: ASHLEY
                    quanPin: Ashley
                    sex: 2
                    remark: 小号
                    remarkPyInitial: XH
                    remarkQuanPin: xiaohao
                    chatRoomNotify: 0
                    signature: 山林不向四季起誓 枯荣随缘。
                    alias: zero-one_200906
                    snsBgImg: >-
                      http://shmmsns.qpic.cn/mmsns/UaAfqYic92wm7ZCrsEwlQMXSmBLs8dpwBzrXnrOyyP3B8bDibCCFInJ9PicC9LPYY17uWH1yIOmBYQ/0
                    bigHeadImgUrl: >-
                      https://wx.qlogo.cn/mmhead/ver_1/buiaXybHTBK3BuGr1edN72zBDermWVFJ7YC8Jib2RcCSdiauAtZcPgUQpdhE9KY5NsumDAWD16fsg3A6OKuhdEr97VAHdTGgk6R1Eibuj7ZNwJ4/0
                    smallHeadImgUrl: >-
                      https://wx.qlogo.cn/mmhead/ver_1/buiaXybHTBK3BuGr1edN72zBDermWVFJ7YC8Jib2RcCSdiauAtZcPgUQpdhE9KY5NsumDAWD16fsg3A6OKuhdEr97VAHdTGgk6R1Eibuj7ZNwJ4/132
                    description: null
                    cardImgUrl: null
                    labelList: '27'
                    country: AD
                    province: null
                    city: null
                    phoneNumList:
                      - "\n\v14752126220"
                    friendUserName: wxid_**********
                    inviterUserName: null
                    memberFlag: null
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/群管理接口
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454720-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
