# 视频-分享到朋友圈

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /sns/sendFinderSns:
    post:
      summary: 视频-分享到朋友圈
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
                allowWxIds:
                  type: array
                  items:
                    type: string
                  title: 允许谁看
                atWxIds:
                  type: array
                  items:
                    type: string
                  title: 提醒谁看
                disableWxIds:
                  type: array
                  items:
                    type: string
                  title: 不给谁看
                id:
                  type: integer
                  title: 视频id
                username:
                  type: string
                  title: 视频作者username
                nickname:
                  type: string
                  title: 视频作者昵称
                headUrl:
                  type: string
                  title: 作者头像
                nonceId:
                  type: string
                  title: nonceId
                mediaType:
                  type: string
                  title: 类型
                width:
                  type: string
                  title: 宽度
                height:
                  type: string
                  title: 高度
                url:
                  type: string
                thumbUrl:
                  type: string
                thumbUrlToken:
                  type: string
                description:
                  type: string
                  title: 视频描述
                videoPlayLen:
                  type: string
                  title: 播放时长
              required:
                - appId
                - allowWxIds
                - atWxIds
                - disableWxIds
                - id
                - username
                - nickname
                - headUrl
                - nonceId
                - mediaType
                - width
                - height
                - url
                - thumbUrl
                - thumbUrlToken
                - description
                - videoPlayLen
              x-apifox-orders:
                - appId
                - allowWxIds
                - atWxIds
                - disableWxIds
                - id
                - username
                - nickname
                - headUrl
                - nonceId
                - mediaType
                - width
                - height
                - url
                - thumbUrl
                - thumbUrlToken
                - description
                - videoPlayLen
            example:
              appId: '{{appid}}'
              useProxy: true
              allowWxIds: []
              atWxIds: []
              disableWxIds: []
              id: 14414431529000
              username: >-
                v2_060000231003b20faec8c7e3ef36b077bc0b9fb41ae2efc82c20ba5fb68f838a@finder
              nickname: 苏生-服务支持
              headUrl: >-
                https://wx.qlogo.cn/finderhead/ver_1/nlibhBXsVzorXqOtGniaqibbThkBtq0RiaILNqtOBcQQm1e16E5WrWF2uFQUDQiaglw0IavDb4eHGPPwp1c1tAF8aZkybLpBVdibRTocbVVeZAD6o/0
              nonceId: '8507486792812551167_0_0_2_2_1724662626395281'
              mediaType: '4'
              width: '1000'
              height: '2000'
              url: >-
                http://wxapp.tc.qq.com/251/20302/stodownload?encfilekey=Cvvj5Ix3eexKX1zo1IZZBrQoSQH1uu2U31EqFp6r4vicWibDJB8iciaEBdZuUC17CsQYbsbayvsu3MXT3QSE4ibicgB2nKU5TAFpxnZBeG3fJrjFN4xxlW1mN0uWtZa5YrwN5ib53OqP497WNcqYtyicvcib2FlISGKIXz6zGB74y4&a=1&dotrans=0&hy=SH&idx=1&m=d0d78a9d4690ba3f16e9b4a8c0192845&uzid=2
              thumbUrl: >-
                http://wxapp.tc.qq.com/251/20350/stodownload?encfilekey=Cvvj5Ix3eexKX1zo1IZZBrQomawrmat=200
              thumbUrlToken: >-
                &token=oA9SZ4icv8It97yyPy38aPOBXibibl3IO9httFyw4ZS02VEgicB6P44BQKVQoQ4uUribzV520RxiaE0aPwM5LPqE6UZyyqtvhLeRl4Hsicib8
              description: '123321#321hh #123哈哈'
              videoPlayLen: '2'
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
                required:
                  - ret
                  - msg
                x-apifox-orders:
                  - ret
                  - msg
              example:
                ret: 200
                msg: 操作成功
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/视频号模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-212068627-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
