# 获取个人资料

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /personal/getProfile:
    post:
      summary: 获取个人资料
      deprecated: false
      description: ''
      tags:
        - 核心 API 模块/个人模块
        - 基础API/个人模块
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
              x-apifox-orders:
                - appId
              required:
                - appId
            example:
              appId: '{{appid}}'
              proxyIp: ''
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
                      alias:
                        type: string
                        description: 微信号
                      wxid:
                        type: string
                        description: 微信ID
                      nickName:
                        type: string
                        description: 昵称
                      mobile:
                        type: string
                        description: 绑定的手机号
                      uin:
                        type: integer
                        description: uin
                      sex:
                        type: integer
                        description: 性别
                      province:
                        type: string
                        description: 省份
                      city:
                        type: string
                        description: 城市
                      signature:
                        type: string
                        description: 签名
                      country:
                        type: string
                        description: 国家
                      bigHeadImgUrl:
                        type: string
                        description: 大尺寸头像
                      smallHeadImgUrl:
                        type: string
                        description: 小尺寸头像
                      regCountry:
                        type: string
                        description: 注册国家
                      snsBgImg:
                        type: string
                        description: 朋友圈背景图
                    required:
                      - alias
                      - wxid
                      - nickName
                      - mobile
                      - uin
                      - sex
                      - province
                      - city
                      - signature
                      - country
                      - bigHeadImgUrl
                      - smallHeadImgUrl
                      - regCountry
                      - snsBgImg
                    x-apifox-orders:
                      - alias
                      - wxid
                      - nickName
                      - mobile
                      - uin
                      - sex
                      - province
                      - city
                      - signature
                      - country
                      - bigHeadImgUrl
                      - smallHeadImgUrl
                      - regCountry
                      - snsBgImg
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
                  alias: null
                  wxid: '***********'
                  nickName: 苏生
                  mobile: '18761670817'
                  uin: 1042679712
                  sex: 1
                  province: Jiangsu
                  city: Xuzhou
                  signature: .......
                  country: CN
                  bigHeadImgUrl: >-
                    https://wx.qlogo.cn/mmhead/ver_1/REoLX7KfdibFAgDbtoeXGNjE6sGa8NCib8UaiazlekKjuLneCvicM4xQpuEbZWjjQooSicsKEbKdhqCOCpTHWtnBqdJicJ0I3CgZumwJ6SxR3ibuNs/0
                  smallHeadImgUrl: >-
                    https://wx.qlogo.cn/mmhead/ver_1/REoLX7KfdibFAgDbtoeXGNjE6sGa8NCib8UaiazlekKjuLneCvicM4xQpuEbZWjjQooSicsKEbKdhqCOCpTHWtnBqdJicJ0I3CgZumwJ6SxR3ibuNs/132
                  regCountry: CN
                  snsBgImg: >-
                    http://shmmsns.qpic.cn/mmsns/FzeKA69P5uIdqPfQxp59LvOohoE2iaiaj86IBH1jl0F76aGvg8AlU7giaMtBhQ3bPibunbhVLb3aEq4/0
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/个人模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454774-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
