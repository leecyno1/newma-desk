# 关注/取消关注

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /finder/follow:
    post:
      summary: 关注/取消关注
      deprecated: false
      description: ''
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
                  description: 自己的roletype
                toUserName:
                  type: string
                  description: 对方的username
                opType:
                  type: integer
                  description: 1:关注   2:取消关注
                searchInfo:
                  type: object
                  properties:
                    cookies:
                      type: string
                    docId:
                      type: string
                    searchId:
                      type: string
                  x-apifox-orders:
                    - cookies
                    - docId
                    - searchId
                  required:
                    - cookies
                    - searchId
                    - docId
                  description: 如果是通过搜索渠道关注，则把搜索接口返回的cookies、searchId、docId传进来
              required:
                - appId
                - myUserName
                - myRoleType
                - opType
                - toUserName
                - searchInfo
              x-apifox-orders:
                - appId
                - myUserName
                - myRoleType
                - toUserName
                - opType
                - searchInfo
            example:
              appId: '{{appid}}'
              useProxy: true
              myUserName: >-
                v2_060000231003b20faec8c7e28811c4d5cc0ded37b0779c48c759a7446a87688c2774e5300c32@finder
              myRoleType: 3
              opType: 1
              toUserName: >-
                v2_060000231003b20faec8c6e18f10c7d6c903ec3db0776955d3d97c6b329d6aa58693bcdb7ad1@finder
              searchInfo:
                cookies: ''
                searchId: ''
                docId: ''
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
                    v2_060000231003b20faec8c6e18f10c7d6c903ec3db0776955d3d97c6b329d6aa58693bcdb7ad1@finder
                  nickname: 朝夕v
                  headUrl: >-
                    https://wx.qlogo.cn/finderhead/ver_1/TDibw5X5xTzpMW9D4GE0YnYUMqPAspF0AibTwhdSFWjyt2tZCMuLVon1PIT6aGulvzvlSZPkDcT06NB6D1eoLicYBKiaBCRDXZJSMEErIGQkQJ8/0
                  signature: 。。。
                  followFlag: 1
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
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/视频号模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454794-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
