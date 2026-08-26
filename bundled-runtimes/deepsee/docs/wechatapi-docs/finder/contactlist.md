# 获取私信人详情

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /finder/contactList:
    post:
      summary: 获取私信人详情
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
                queryInfo:
                  type: string
                  description: 联系人的username
              required:
                - appId
                - myUserName
                - myRoleType
                - queryInfo
              x-apifox-orders:
                - appId
                - myUserName
                - myRoleType
                - queryInfo
            example:
              appId: '{{appid}}'
              myUserName: >-
                v2_060000231003b20faec8c6e58e1fc1d5cf06ed35b07774395a04f79f4e39faa121ac3df32ce4@finder
              queryInfo: >-
                fv1_13488a650d26c9894b02aa91e172e95cab47367888ff75ada44e0063e7c3cc26@findermsgstranger
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
                    type: array
                    items:
                      type: object
                      properties:
                        username:
                          type: string
                          description: 联系人的username
                        nickname:
                          type: string
                          description: 昵称
                        headUrl:
                          type: string
                          description: 头像
                        signature:
                          type: string
                          description: 简介
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
                          description: 扩展信息
                          x-apifox-orders:
                            - country
                            - province
                            - city
                            - sex
                        msgInfo:
                          type: object
                          properties:
                            msgUsername:
                              type: string
                            sessionId:
                              type: string
                              description: 发送私信时用到的sessionid
                          required:
                            - msgUsername
                            - sessionId
                          x-apifox-orders:
                            - msgUsername
                            - sessionId
                        wxUsernameV5:
                          type: string
                      x-apifox-orders:
                        - username
                        - nickname
                        - headUrl
                        - signature
                        - extInfo
                        - msgInfo
                        - wxUsernameV5
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
                  - username: >-
                      fv1_13488a650d26c9894b02aa91e172e95cab47367888ff75ada44e0063e7c3cc26@findermsgstranger
                    nickname: 苏生-服务支持
                    headUrl: >-
                      https://wx.qlogo.cn/mmhead/ver_1/h4JicWMXQVJ3sTKJqCGa37zV90RIhBRZKwML0j1ynsVwLXw1ms884aLOCIVvu3y5RkbKicdDcq14jmyKdQHarVu3yfM9wIjibd1YDF6NZLEBxkqsAeZFfFGZXAN2e2shxllWBVu19LcL61eP1WgzYgx0Q/132
                    signature: ''
                    extInfo:
                      country: CN
                      province: Zhejiang
                      city: Hangzhou
                      sex: 0
                    msgInfo:
                      msgUsername: >-
                        fv1_13488a650d26c9894b02aa91e172e95cab47367888ff75ada44e0063e7c3cc26@findermsgstranger
                      sessionId: >-
                        13488a650d26c9894b02aa91e172e95cab47367888ff75ada44e0063e7c3cc26@findermsg
                    wxUsernameV5: >-
                      v5_020b0a16610401000000000048ba0ecad83e63000000b1afa7d8728e3dd43ef4317a780e33c263e61215355656ddf5124a5d6d13ad1957a710c2bcdc777f48a5f7e94490f7665d0a5822940c6c91ec2e5179cf5844040019bedd86a99632a490fc05da@stranger
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/视频号模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-207256349-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
