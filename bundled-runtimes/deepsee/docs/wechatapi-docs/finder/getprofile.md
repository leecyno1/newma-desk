# 获取视频号信息

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /finder/getProfile:
    post:
      summary: 获取视频号信息
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
              required:
                - appId
              x-apifox-orders:
                - appId
            example:
              appId: '{{appid}}'
              useProxy: true
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
                      signatureMaxLength:
                        type: integer
                        description: 简介内容最大长度
                      nicknameMinLength:
                        type: integer
                        description: 昵称最小长度
                      nicknameMaxLength:
                        type: integer
                        description: 昵称最大长度
                      userNoFinder:
                        type: integer
                      purchasedTotalCount:
                        type: integer
                      privacySetting:
                        type: object
                        properties:
                          exportJumpLink:
                            type: string
                        required:
                          - exportJumpLink
                        x-apifox-orders:
                          - exportJumpLink
                        description: 隐私设置
                      aliasInfo:
                        type: array
                        items:
                          type: object
                          properties:
                            nickname:
                              type: string
                              description: 昵称
                            headImgUrl:
                              type: string
                              description: 头像
                            roleType:
                              type: integer
                              description: 身份类型：1：微信、3：视频号
                          required:
                            - nickname
                            - headImgUrl
                            - roleType
                          x-apifox-orders:
                            - nickname
                            - headImgUrl
                            - roleType
                        description: 身份信息
                      currentAliasRoleType:
                        type: integer
                        description: 当前身份类型
                      nextAliasModAvailableTime:
                        type: integer
                      actionWording:
                        type: object
                        properties: {}
                        x-apifox-orders: []
                      userFlag:
                        type: integer
                      mainFinderUsername:
                        type: string
                        description: 视频号的username
                    required:
                      - mainFinderUsername
                      - signatureMaxLength
                      - nicknameMinLength
                      - nicknameMaxLength
                      - userNoFinder
                      - purchasedTotalCount
                      - privacySetting
                      - aliasInfo
                      - currentAliasRoleType
                      - nextAliasModAvailableTime
                      - actionWording
                      - userFlag
                    x-apifox-orders:
                      - signatureMaxLength
                      - nicknameMinLength
                      - nicknameMaxLength
                      - userNoFinder
                      - purchasedTotalCount
                      - privacySetting
                      - aliasInfo
                      - currentAliasRoleType
                      - nextAliasModAvailableTime
                      - actionWording
                      - userFlag
                      - mainFinderUsername
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
                  mainFinderUsername: >-
                    v2_060000231003b20faec8cae7811bcadcc904efb0770fd600f70cfec5c128fc2ef6421e0c7a@finder
                  signatureMaxLength: 400
                  nicknameMinLength: 2
                  nicknameMaxLength: 30
                  userNoFinder: 0
                  purchasedTotalCount: 0
                  privacySetting:
                    exportJumpLink: >-
                      https://channels.weixin.qq.com/pdora/pages/biz-binding/exportdata.html
                  aliasInfo:
                    - nickname: 苏生-服务支持
                      headImgUrl: >-
                        http://wx.qlogo.cn/mmhead/KydxAIB52xko9wNI4ias31aD9VtZOMr0NANibM6i5aHia40picngZg9tv2tk3ibID640oKc45NWIAkM/0
                      roleType: 1
                    - nickname: 苏生-服务支持
                      headImgUrl: >-
                        http://wx.qlogo.cn/finderhead/KydxAIB52xko9wNI4ias31X8kT3V99AyBwiamVfsoTfpCEXsOfLEVk6fX6hJd9mLeYyBrk1DZhc/0
                      roleType: 3
                  currentAliasRoleType: 3
                  nextAliasModAvailableTime: 0
                  actionWording: {}
                  userFlag: 20
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/视频号模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454785-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
