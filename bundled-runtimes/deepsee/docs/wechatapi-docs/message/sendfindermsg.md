# 视频-分享给好友

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /message/sendFinderMsg:
    post:
      summary: 视频-分享给好友
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
                toWxid:
                  type: string
                  description: 接收人wxid
                id:
                  type: integer
                  description: 视频信息id
                username:
                  type: string
                  description: 视频发布者username
                nickname:
                  type: string
                  description: 视频发布者昵称
                headUrl:
                  type: string
                  description: 视频发布者头像
                nonceId:
                  type: string
                  description: 视频nonceId
                mediaType:
                  type: string
                  description: 视频类型
                width:
                  type: string
                  description: 视频宽度
                height:
                  type: string
                  description: 视频高度
                url:
                  type: string
                  description: url
                thumbUrl:
                  type: string
                  description: thumbUrl
                thumbUrlToken:
                  type: string
                  description: thumbUrlToken
                description:
                  type: string
                  description: 视频描述
                videoPlayLen:
                  type: string
                  description: 播放时长
              required:
                - appId
                - toWxid
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
                - toWxid
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
              toWxid: ''
              id: 1441443711529000
              username: >-
                v2_060000231003b20faec8c7e08f******6b077bc0b9fb41ae2efc82c20ba5fb68f838a@finder
              nickname: 苏生-服务支持
              headUrl: >-
                https://wx.qlogo.cn/finderhead/ver_1/nlibhBXsVzorXqOtGniaqibbThkBtq0RiaILNqtOBcQQm1e16E5WrWF2uFQUDQiaglw0IavDb4eHGPPwp1c1tAF8aZkybLpBVdibRTocbVVeZAD6o/0
              nonceId: 850748679****2551167_0_0_2_2_1724662626395281
              mediaType: '4'
              width: '1000'
              height: '2000'
              url: >-
                http://wxapp.tc.qq.com/251/20302/stodownload?encfilekey=Cvvj5Ix3eexKX1zo1IrwN5ib53OqP497WNcqYtyicvcib2FlISGKIXz6zGB74y4&a=1&dotrans=0&hy=SH&idx=1&m=d0d78a9d4690ba3f16e9b4a8c0192845&uzid=2
              thumbUrl: >-
                http://wxapp.tc.qq.com/251/20350/stodownload?encfilekey=Cvvj5Ix3eexKX1zo1IZZBrQRE1J2AleALLHCsQOz0eNbTaD5Bbic3CEwZY&dotrans=0&hy=SH&idx=1&m=0babaadbda6c96767df974ce651bc42f&picformat=200
              thumbUrlToken: >-
                &token=oA9SZ4icv8It97yyPy38aPOBXibibl3IO9EqgicB6P44BQKVQoQ4uUribzV520RxiaE0aPwM5LPqE6UZyyqtvhLeRl4Hsicib8
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
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-212068626-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
