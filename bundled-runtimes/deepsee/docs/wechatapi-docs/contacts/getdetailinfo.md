# 获取群/好友详细信息

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /contacts/getDetailInfo:
    post:
      summary: 获取群/好友详细信息
      deprecated: false
      description: ''
      tags:
        - 核心 API 模块/联系人相关接口
        - 基础API/联系人模块
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
                wxids:
                  type: array
                  items:
                    type: string
                    description: 好友的wxid
                  description: 好友的wxid
                  minItems: 1
                  maxItems: 20
              x-apifox-orders:
                - appId
                - wxids
              required:
                - appId
                - wxids
            example: |-
              //单个好友/群
              {
                  "appId": "{{appid}}",
                  "wxids": [
                      "wechatapi"
                  ]
              }
              //多个好友/群
              {
                  "appId": "{{appid}}",
                  "wxids": [
                      "ier****isi",
                      "kit****622",
                      "F10****0104",
                      "leo****001",
                      "kel****0428",
                      "wxi****612",
                      "wxi****522"
                  ]
              }
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
                          description: 好友的wxid
                        nickName:
                          type: string
                          description: 好友的昵称
                        pyInitial:
                          type: 'null'
                          description: 好友昵称的拼音首字母
                        quanPin:
                          type: string
                          description: 好友昵称的全拼
                        sex:
                          type: integer
                          description: 好友的性别
                        remark:
                          type: 'null'
                          description: 好友备注
                        remarkPyInitial:
                          type: 'null'
                          description: 好友备注的拼音首字母
                        remarkQuanPin:
                          type: 'null'
                          description: 好友备注的全拼
                        signature:
                          type: string
                          description: 好友的签名
                        alias:
                          type: string
                          description: 好友的微信号
                        snsBgImg:
                          type: string
                          description: 朋友圈背景图链接
                        country:
                          type: string
                          description: 国家
                        bigHeadImgUrl:
                          type: string
                          description: 大尺寸头像链接
                        smallHeadImgUrl:
                          type: string
                          description: 小尺寸头像链接
                        description:
                          type: 'null'
                          description: 好友的描述
                        cardImgUrl:
                          type: 'null'
                          description: 好友描述的图片链接
                        labelList:
                          type: 'null'
                          description: 好友的标签ID
                        province:
                          type: 'null'
                          description: 省份
                        city:
                          type: 'null'
                          description: 城市
                        phoneNumList:
                          type: 'null'
                          description: 好友的手机号码
                      x-apifox-orders:
                        - userName
                        - nickName
                        - pyInitial
                        - quanPin
                        - sex
                        - remark
                        - remarkPyInitial
                        - remarkQuanPin
                        - signature
                        - alias
                        - snsBgImg
                        - country
                        - bigHeadImgUrl
                        - smallHeadImgUrl
                        - description
                        - cardImgUrl
                        - labelList
                        - province
                        - city
                        - phoneNumList
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
                msg: 获取联系人信息成功
                data:
                  - userName: wxid_**********
                    nickName: Ashley
                    pyInitial: null
                    quanPin: Ashley
                    sex: 2
                    remark: null
                    remarkPyInitial: null
                    remarkQuanPin: null
                    signature: 山林不向四季起誓 枯荣随缘。
                    alias: zero-one_200906
                    snsBgImg: >-
                      http://shmmsns.qpic.cn/mmsns/UaAfqYic92wm7ZCrsEwlQMXSmBLs8dpwBzrXnrOyyP3B8bDibCCFInJ9PicC9LPYY17uWH1yIOmBYQ/0
                    country: AD
                    bigHeadImgUrl: >-
                      https://wx.qlogo.cn/mmhead/ver_1/buiaXybHTBK3BuGr1edN72zBDermWVFJ7YC8Jib2RcCSdiauAtZcPgUQpdhE9KY5NsumDAWD16fsg3A6OKuhdEr97VAHdTGgk6R1Eibuj7ZNwJ4/0
                    smallHeadImgUrl: >-
                      https://wx.qlogo.cn/mmhead/ver_1/buiaXybHTBK3BuGr1edN72zBDermWVFJ7YC8Jib2RcCSdiauAtZcPgUQpdhE9KY5NsumDAWD16fsg3A6OKuhdEr97VAHdTGgk6R1Eibuj7ZNwJ4/132
                    description: null
                    cardImgUrl: null
                    labelList: null
                    province: null
                    city: null
                    phoneNumList: null
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/联系人相关接口
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454704-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
