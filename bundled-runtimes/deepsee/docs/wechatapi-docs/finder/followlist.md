# 关注列表

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /finder/followList:
    post:
      summary: 关注列表
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
                  description: 设备ID
                myUserName:
                  type: string
                  description: 自己的username
                myRoleType:
                  type: integer
                  description: 自己的roletype
                lastBuffer:
                  type: string
                  description: 首次传空，后续传接口返回的lastBuffer
              required:
                - appId
                - myUserName
                - myRoleType
              x-apifox-orders:
                - appId
                - myUserName
                - myRoleType
                - lastBuffer
            example:
              appId: '{{appid}}'
              useProxy: true
              myUserName: '{{userName}}'
              lastBuffer: ''
              myRoleType: 3
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
                      contactList:
                        type: array
                        items:
                          type: object
                          properties:
                            username:
                              type: string
                            nickname:
                              type: string
                            headUrl:
                              type: string
                            signature:
                              type: string
                            followFlag:
                              type: integer
                            followTime:
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
                                country:
                                  type: string
                                province:
                                  type: string
                                city:
                                  type: string
                              required:
                                - country
                                - province
                                - city
                                - sex
                              x-apifox-orders:
                                - sex
                                - country
                                - province
                                - city
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
                            - followTime
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
                            - followTime
                            - authInfo
                            - coverImgUrl
                            - spamStatus
                            - extFlag
                            - extInfo
                            - liveStatus
                            - liveCoverImgUrl
                            - liveInfo
                            - status
                      lastBuffer:
                        type: string
                      continueFlag:
                        type: integer
                      followCount:
                        type: integer
                    required:
                      - contactList
                      - lastBuffer
                      - continueFlag
                      - followCount
                    x-apifox-orders:
                      - contactList
                      - lastBuffer
                      - continueFlag
                      - followCount
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
                  contactList:
                    - username: >-
                        v2_060000231003b20faec8c7e28811c4d5cc0ded37b0779c48c759a7446a87688c2774e5300c32@finder
                      nickname: 未来可期啊哈
                      headUrl: >-
                        https://wx.qlogo.cn/finderhead/ver_1/D5kOMSrTOprOibFVZ2NOO8AnohFdlDMhoNTZr1C8D9d5K6og92mcc3lxDEFcQldBibqjzIx2iavenQO0TMzhjmrUibmn3iaoaLYtNiaGFWjZgCd5t92shsicTvcyiaIjFjRtwVgy/0
                      signature: 理智，清醒，知进退。
                      followFlag: 1
                      followTime: 1706090194
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
                    - username: >-
                        v2_060000231003b20faec8c6e18f10c7d6c903ec3db0776955d3d97c6b329d6aa58693bcdb7ad1@finder
                      nickname: 朝夕v
                      headUrl: >-
                        https://wx.qlogo.cn/finderhead/ver_1/TDibw5X5xTzpMW9D4GE0YnYUMqPAspF0AibTwhdSFWjyt2tZCMuLVon1PIT6aGulvzvlSZPkDcT06NB6D1eoLicYBKiaBCRDXZJSMEErIGQkQJ8/0
                      signature: 。。。
                      followFlag: 1
                      followTime: 1706086669
                      authInfo: {}
                      coverImgUrl: ''
                      spamStatus: 0
                      extFlag: 262156
                      extInfo:
                        country: CN
                        province: Jiangsu
                        city: Xuzhou
                        sex: 2
                      liveStatus: 2
                      liveCoverImgUrl: >-
                        http://wxapp.tc.qq.com/251/20350/stodownload?m=be88b1cb981aa72b3328ccbd22a58e0b&filekey=30340201010420301e020200fb040253480410be88b1cb981aa72b3328ccbd22a58e0b02022814040d00000004627466730000000132&hy=SH&storeid=5649443df0009b8a38399cc84000000fb00004f7e534815c008e0b08dc805c&dotrans=0&bizid=1023
                      liveInfo:
                        anchorStatusFlag: 133248
                        switchFlag: 53727
                        lotterySetting:
                          settingFlag: 0
                          attendType: 4
                      status: 0
                  lastBuffer: COMF
                  continueFlag: 0
                  followCount: 2
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/视频号模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454803-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
