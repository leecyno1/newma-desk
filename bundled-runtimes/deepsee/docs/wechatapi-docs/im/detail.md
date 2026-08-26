# 获取企微好友详情

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /im/detail:
    post:
      summary: 获取企微好友详情
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
                toUserName:
                  type: string
                  description: 企业微信号
              x-apifox-orders:
                - appId
                - toUserName
              required:
                - appId
                - toUserName
            example:
              appId: '{{appid}}'
              toUserName: 259962145****456301@openim
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
                      userName:
                        type: string
                        description: 企业微信号
                      nickName:
                        type: string
                        description: 企业微信昵称
                      remark:
                        type: string
                        description: 备注
                      bigHeadImg:
                        type: string
                        description: 大头像
                      smallHeadImg:
                        type: string
                        description: 小头像
                      appId:
                        type: string
                        description: 企业微信APPID
                      descWordingId:
                        type: string
                        description: 企业ID
                      wording:
                        type: string
                        description: 企业全称
                      wordingPinyin:
                        type: string
                        description: 企业全称拼音
                      wordingQuanpin:
                        type: string
                        description: 企业名称全拼
                    x-apifox-orders:
                      - userName
                      - nickName
                      - remark
                      - bigHeadImg
                      - smallHeadImg
                      - appId
                      - descWordingId
                      - wording
                      - wordingPinyin
                      - wordingQuanpin
                    required:
                      - userName
                      - nickName
                      - remark
                      - bigHeadImg
                      - smallHeadImg
                      - appId
                      - descWordingId
                      - wording
                      - wordingPinyin
                      - wordingQuanpin
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
                  userName: 685992**236
                  nickName: '******'
                  remark: ''
                  bigHeadImg: http://wew**qpoCghewE/
                  smallHeadImg: http://**sapevHrU/
                  appId: 56****635
                  descWordingId: EDFYH9F68S8**aewax
                  wording: '******'
                  wordingPinyin: '******'
                  wordingQuanpin: '******'
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/联系人相关接口
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-176184393-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
