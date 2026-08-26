# 扫码关注

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /finder/scanFollow:
    post:
      summary: 扫码关注
      deprecated: false
      description: ''
      tags:
        - 核心 API 模块/视频号模块
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
                proxyIp:
                  type: string
                myUserName:
                  type: string
                  description: 当前用户的userName
                myRoleType:
                  type: integer
                  description: 身份类型 1：微信 3：视频号
                qrContent:
                  type: string
                  description: 内容信息 二维码链接或对方的userName
                objectId:
                  type: string
                  description: 如果qrContent 为对方userName 则参数必传，内容从用户主页获取
                objectNonceId:
                  type: string
                  description: 如果qrContent 为对方userName 则参数必传，内容从用户主页获取
              required:
                - appId
                - proxyIp
                - myUserName
                - myRoleType
                - qrContent
                - objectId
                - objectNonceId
              x-apifox-orders:
                - appId
                - proxyIp
                - myUserName
                - myRoleType
                - qrContent
                - objectId
                - objectNonceId
            example:
              appId: '{{appid}}'
              useProxy: true
              myUserName: v2_060000231003b**8c759a74488c2774e5300c32@finder
              myRoleType: 3
              qrContent: v2_060000231003**465d77bc19b96ccee6e@finder
              objectId: 144487526**8757
              objectNonceId: 16839900**8113015869
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
                      username:
                        type: string
                        description: 对方的username
                      nickname:
                        type: string
                        description: 昵称
                      headUrl:
                        type: string
                        description: 头像
                      signature:
                        type: string
                        description: 简介
                      followFlag:
                        type: integer
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
                          sex:
                            type: integer
                            description: 性别
                        required:
                          - sex
                        x-apifox-orders:
                          - sex
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
                      - signature
                      - followFlag
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
                      - signature
                      - followFlag
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
                  username: >-
                    v2_060000231003b20faec8c7e28811c4d5cc0ded779c48c759a7446a87688c2774e5300c32@finder
                  nickname: 苏生-服务支持
                  headUrl: >-
                    https://wx.qlogo.cn/finderhead/ver_1/D5kOMSrTOprOibFVZ2NOO8AnohFdlDMhoNTZr1C8D9og92mcc3lxDEFcQldBibqjzIx2iavenQO0TMzhjmrUibmn3iaoaLYtNiaGFWjZgCd5t92shsicTvcyiaIjFjRtwVgy/0
                  signature: VideosApi。
                  followFlag: 1
                  authInfo: {}
                  coverImgUrl: ''
                  spamStatus: 0
                  extFlag: 262152
                  extInfo:
                    sex: 1
                  liveStatus: 2
                  liveCoverImgUrl: ''
                  liveInfo:
                    anchorStatusFlag: 2048
                    switchFlag: 53727
                    lotterySetting:
                      settingFlag: 0
                      attendType: 4
                  status: 0
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/视频号模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-231367784-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
