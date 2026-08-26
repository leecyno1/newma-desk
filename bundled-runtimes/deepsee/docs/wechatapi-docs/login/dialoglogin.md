# 弹框登录

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /login/dialogLogin:
    post:
      summary: 弹框登录
      deprecated: false
      description: >-
        -
        调用本接口后手机会弹框确认登录页面，点确认后调用[执行登录接口](https://post.wechatapi.net/login/checklogin)检测是否登录成功



        - 若目前支持的regionId中没有您所在的地区，可以自行采购socks5协议代理IP，填写到proxyIp参数中

        - 使用本接口登录并非100%成功，本接口返回失败后，可通过扫码登录的方式登录
            - 以下几种情况无法使用本接口登录：
                - 手机点击退出登录
                - 新设备登录次日
                - 官方风控下线
      tags:
        - 核心 API 模块/登录模块
        - 基础API/登录模块
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
                proxyIp:
                  type: string
                  description: 代理IP 格式：socks5://username:password@123.2.2.2
                  additionalProperties: false
                regionId:
                  type: string
                  description: >-
                    地区ID

                    地区ID在前，地区在后*
                      ```java HelloWorld.java
                    110000*北京市|120000*天津市|130000*河北省|140000*山西省|150000*内蒙古

                    210000*辽宁省|220000*吉林省|230000*黑龙江

                    310000*上海市|320000*江苏省|330000*浙江省|340000*安徽省|350000*福建省|360000*江西省|370000*山东省

                    410000*河南省|420000*湖北省|430000*湖南省|440000*广东省|450000*广西省|460000*海南省

                    500000*重庆市|510000*四川省|520000*贵州省|530000*云南省|540000*西藏自治区

                    610000*陕西省|620000*甘肃省|630000*青海省|640000*宁夏自治区|650000*新疆自治区
                      ```
                  additionalProperties: false
              x-apifox-orders:
                - appId
                - proxyIp
                - regionId
              required:
                - appId
                - proxyIp
                - regionId
            example:
              appId: '{appid}'
              proxyIp: ''
              regionId: '{regionId}'
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
                      appId:
                        type: string
                        description: 设备ID
                      uuid:
                        type: string
                        description: 二维码uuid，执行登录时会用到
                    required:
                      - appId
                      - uuid
                    description: 响应数据
                    x-apifox-orders:
                      - appId
                      - uuid
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
                  appId: wx_wR_U4zPj2M_OTS3BCyoE4
                  uuid: 4dmHZZMtoLbHoLZwd1wE
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/登录模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454695-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
