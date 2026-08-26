# (步骤2)执行登录

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /login/checkLogin:
    post:
      summary: (步骤2)执行登录
      deprecated: false
      description: >
        - 获取登录二维码**扫码之后**需**每间隔5s调用本接口**来判断是否登录成功，**二维码超时时间为120秒**

        **- 登录成功后logininfo有数据，如果没有数据则需要一直执行，直至出现登录数据或者失败为止。**

        -
        新设备登录平台，次日凌晨会掉线一次，重新登录时需调用[获取二维码且传appId取码](https://post.wechatapi.net/login/getloginqrcode)，登录成功后则可以长期在线

        - 登录成功后请保存appId与wxid的对应关系，后续接口中会用到





        <Tabs>
          <Tab title="iPad登录" >
            ☝️ 首次登录iPad出现**新设备验证**并且**无数字验证码**此时本接口会返回一个二维码网址，开发者需使用IOS设备下载[认证APP](https://www.pgyer.com/renzhengapp)扫描二维码网址，扫描人脸通过后，再次调用本接口，手机点击确认，则本接口返回登录结果。如果不进行人脸认证则需要切换Mac登录，请查看Mac登录流程
            ☝️ 首次登录iPad出现**新设备验证**并且**有数字验证码**直接在captchCode字段输入数字验证码，继续执行登录即可登录。
              
              
              
        <Accordion title="iPad登录流程图，不清楚流程必看，点击此处"  defaultOpen={false}
        icon="lucide-smartphone" >



        <Frame caption="iPad登录流程图，不清楚流程必看">


        ![image.png](https://api.apifox.com/api/v1/projects/4425884/resources/590083/image-preview)

        </Frame>



        </Accordion>

          </Tab>
            
            
          <Tab title="Mac登录">
            ☝️  首次登录Mac如果出现新设备验证，可以**选择自动验证**，不需要下载APP。
            ☝️    如果**不选择自动验证**会返回URL。生成二维码之后，需要使用[安卓设备下载APP](https://www.pgyer.com/sdyanzheng-android)，扫码进行图形验证。操作完成后继续调用此接口即可通过新设备验证。
            ☝️用户若有自己平台App，则可代码接入，无需下载App
              
        <Accordion title="Mac登录流程图，不清楚流程必看，点击此处" defaultOpen={false} Icon
        icon="lucide-airplay">

            <Frame caption="Mac登录流程图，不清楚流程必看">
        ![Mac登录.png](https://api.apifox.com/api/v1/projects/4425884/resources/581306/image-preview)

        </Frame>




        </Accordion>

          </Tab>
        </Tabs>
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
                  description: |-
                    设备ID
                    获取二维码接口返回的appId
                  additionalProperties: false
                proxyIp:
                  type: string
                  description: |-
                    代理IP 
                    格式：socks5://username:password@123.2.2.2
                  additionalProperties: false
                uuid:
                  type: string
                  description: 获取二维码返回的uuid
                  additionalProperties: false
                captchCode:
                  type: string
                  description: 扫码后手机提示输入的验证码，如未提示数字验证码可不传此字段。
                autoSliding:
                  type: boolean
                  description: |-
                    是否自动验证true/false，仅限mac使用。
                    true为自动验证，false需要用app扫码验证。
                    如果类型为ipad登录时必须传false。
              x-apifox-orders:
                - appId
                - proxyIp
                - uuid
                - captchCode
                - autoSliding
              required:
                - appId
                - uuid
                - autoSliding
            example:
              appId: '{appid}'
              uuid: '{uuid}'
              autoSliding: true
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
                      uuid:
                        type: string
                        description: 二维码的uuid
                      headImgUrl:
                        type: string
                        description: 头像地址
                      nickName:
                        type: string
                        description: 昵称
                      expiredTime:
                        type: integer
                        description: 二维码超时时间
                      status:
                        type: integer
                        description: |
                          登录状态 0：未扫码 1：已扫码未登录 2：登录成功 4：已扫码取消登录
                      loginInfo:
                        type: object
                        properties:
                          uin:
                            type: integer
                            description: uin
                          wxid:
                            type: string
                            description: 微信ID，返回此值则是登录成功
                          nickName:
                            type: string
                            description: 昵称
                          mobile:
                            type: string
                            description: 绑定的手机号
                          alias:
                            type: string
                            description: 微信号
                        required:
                          - uin
                          - wxid
                          - nickName
                          - mobile
                          - alias
                        x-apifox-orders:
                          - uin
                          - wxid
                          - nickName
                          - mobile
                          - alias
                        description: 登录成功信息
                    required:
                      - uuid
                      - headImgUrl
                      - nickName
                      - expiredTime
                      - status
                      - loginInfo
                    description: 响应数据
                    x-apifox-orders:
                      - uuid
                      - headImgUrl
                      - nickName
                      - expiredTime
                      - status
                      - loginInfo
                required:
                  - ret
                  - msg
                  - data
                x-apifox-orders:
                  - ret
                  - msg
                  - data
              examples:
                '1':
                  summary: 扫码但未点确认时的响应
                  value: |-
                    {
                        "ret": 200,
                        "msg": "操作成功",
                        "data": {
                            "uuid": "AfPV********5Mr",
                            "headImgUrl": "http://wx.qlogo.c****D/0",
                            "nickName": "苏生-服务支持",
                            "expiredTime": 201,
                            "status": 1,
                            "loginInfo": null
                        }
                    }
                    //* 需要图形验证时返回,直接打开链接扫描二维码，使用app扫描验证
                    {
                        "ret": 200,
                        "msg": "操作成功",
                        "data": {
                            "url": "http://api.asilu.com/qrcode/?t=http://182.40.196.1:8123/s/01K585Y35QPBXD6JMZSNHJZAPZ"
                        }
                    }
                '2':
                  summary: 登录成功
                  value: |-
                    {
                        "ret": 200,
                        "msg": "操作成功",
                        "data": {
                            "uuid": "obOt*******y-Td_X",
                            "headImgUrl": "http://wx.qlogo.cn/mmhead/ver_1/CUPTtZ1ZwiccmeNbxsl8ZaIjWabEoC4bovqxdIszpicEjn8VXayic1dAIT02yJnThun5I9PYjIdCzhQXWglLKh68ibZUCmMzk0YXMDRic1VahOnOjRCA6WtaQPiaeatGtbMIRw6CPsNh7fic4RDyq5bicplQ7Q/0",
                            "nickName": "苏生-服务支持",
                            "expiredTime": 187,
                            "status": 2,
                            "loginInfo": {
                                "uin": 27****0204,
                                "wxid": "wxid_mu****0j7522",
                                "nickName": "苏生-服务支持",
                                "mobile": "1*******836",
                                "alias": "VideosApi"
                            }
                        }
                    }
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/登录模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454694-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
