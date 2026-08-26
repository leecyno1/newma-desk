# 获取手机通讯录

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /contacts/getPhoneAddressList:
    post:
      summary: 获取手机通讯录
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
                phones:
                  type: array
                  items:
                    type: string
                    description: 手机号
                  description: 获取哪些手机号的好友详情，不传获取所有
              x-apifox-orders:
                - appId
                - phones
              required:
                - appId
            example:
              appId: '{{appid}}'
              phones: []
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
                        v4:
                          type: 'null'
                        nickName:
                          type: 'null'
                        sex:
                          type: integer
                        phoneMd5:
                          type: string
                        signature:
                          type: string
                        alias:
                          type: 'null'
                        country:
                          type: string
                        bigHeadImgUrl:
                          type: string
                        smallHeadImgUrl:
                          type: string
                        province:
                          type: string
                        city:
                          type: string
                        personalCard:
                          type: integer
                      x-apifox-orders:
                        - userName
                        - v4
                        - nickName
                        - sex
                        - phoneMd5
                        - signature
                        - alias
                        - country
                        - bigHeadImgUrl
                        - smallHeadImgUrl
                        - province
                        - city
                        - personalCard
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
                msg: 获取手机通讯录成功
                data:
                  - userName: wxid_ddgsghdfafaphh22
                    v4: null
                    nickName: null
                    sex: 1
                    phoneMd5: d36f4cc1c8bca1ef41b93d2215133cdb
                    signature: ......
                    alias: null
                    country: CN
                    bigHeadImgUrl: >-
                      http://wx.qlogo.cn/mmhead/ver_1/vwGdLRK5jtpXagA7dfXlUiaU9VayWNSqia1c2Wib7icJNhPd6WHhqMIVuYuNDfEqPRC2TnmlRSkfYrib9fHyYONwdccv17gibCls7ia8elaunvgMmYicAw22wUJQ3CDw0Cm5ibrOT/0
                    smallHeadImgUrl: >-
                      http://wx.qlogo.cn/mmhead/ver_1/vwGdLRK5jtpXagA7dfXlUiaU9VayWNSqia1c2Wib7icJNhPd6WHhqMIVuYuNDfEqPRC2TnmlRSkfYrib9fHyYONwdccv17gibCls7ia8elaunvgMmYicAw22wUJQ3CDw0Cm5ibrOT/132
                    province: Jiangsu
                    city: Xuzhou
                    personalCard: 0
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/联系人相关接口
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454708-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
