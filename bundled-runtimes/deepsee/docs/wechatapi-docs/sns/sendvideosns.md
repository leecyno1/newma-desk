# 发送视频朋友圈

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /sns/sendVideoSns:
    post:
      summary: 发送视频朋友圈
      deprecated: false
      description: >-
        在新设备登录后的1-3天内，您将无法使用朋友圈发布、点赞、评论等功能。在此期间，如果尝试进行这些操作，您将收到来自微信团队的提醒。请注意遵守相关规定。


        #### 注意

        本接口的videoInfo参数需通过
        [上传朋友圈视频接口](https://post.wechatapi.net/sns/uploadsnsvideo) 获取
      tags:
        - 核心 API 模块/朋友圈模块
        - 基础API/朋友圈模块
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
                allowWxIds:
                  type: array
                  items:
                    type: string
                    description: 好友的wxid
                  description: 允许谁看
                atWxIds:
                  type: array
                  items:
                    type: string
                    description: 好友的wxid
                  description: 提醒谁看
                disableWxIds:
                  type: array
                  items:
                    type: string
                    description: 好友的wxid
                  description: 不给谁看
                privacy:
                  type: boolean
                  description: 是否私密
                  default: 'false'
                content:
                  type: string
                  description: 朋友圈文字内容
                videoInfo:
                  type: object
                  properties:
                    fileUrl:
                      type: string
                    thumbUrl:
                      type: string
                    fileMd5:
                      type: string
                    length:
                      type: number
                  x-apifox-orders:
                    - fileUrl
                    - thumbUrl
                    - fileMd5
                    - length
                  required:
                    - fileUrl
                    - fileMd5
                    - thumbUrl
                  description: 通过上传朋友圈视频接口获取
              x-apifox-orders:
                - appId
                - allowWxIds
                - atWxIds
                - disableWxIds
                - privacy
                - content
                - videoInfo
              required:
                - appId
                - videoInfo
            example:
              appId: '{{appid}}'
              allowWxIds: []
              atWxIds: []
              disableWxIds: []
              content: in
              videoInfo:
                fileUrl: >-
                  http://szzjwxsns.video.qq.com/102/20202/snsvideodownload?filekey=30340201010420301e0201660402535a04106e95f9d79588843ac259b780f0cbf20f020314148b040d00000004627466730000000132&hy=SZ&storeid=5658e7541000080a98399cc840000006600004eea535a236b0181565ff0c9a&dotrans=9&ef=30_0&ut=6xykWLEnztInqJIccsNnmJnFIIMYTDicqsNxakAGmcmW1hOicyiayN6Cw&ui=1&bizid=1023&ilogo=2&dur=7&upid=500030
                thumbUrl: >-
                  http://vweixinthumb.tc.qq.com/150/20250/snsvideodownload?filekey=30340201010420301e020200960402535a0410704de7ebbc107a51a4f0986253a6d3b602020448040d00000004627466730000000132&hy=SZ&storeid=5658e7541000065838399cc840000009600004f1a535a236cc15156605b59d&bizid=1023
                fileMd5: 6e95f9d79588843ac259b780f0cbf20f
                length: 1315979
              privacy: false
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
                      id:
                        type: integer
                        description: 朋友圈ID
                      userName:
                        type: string
                        description: 朋友圈作者的wxid
                      nickName:
                        type: string
                        description: 朋友圈作者的昵称
                      createTime:
                        type: integer
                        description: 发布时间
                    required:
                      - id
                      - userName
                      - nickName
                      - createTime
                    x-apifox-orders:
                      - id
                      - userName
                      - nickName
                      - createTime
                required:
                  - ret
                  - msg
                  - data
                x-apifox-orders:
                  - ret
                  - msg
                  - data
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/朋友圈模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454761-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
