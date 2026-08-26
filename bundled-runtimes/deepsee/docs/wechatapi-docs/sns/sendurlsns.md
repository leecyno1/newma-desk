# 发送链接朋友圈

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /sns/sendUrlSns:
    post:
      summary: 发送链接朋友圈
      deprecated: false
      description: >-
        在新设备登录后的1-3天内，您将无法使用朋友圈发布、点赞、评论等功能。在此期间，如果尝试进行这些操作，您将收到来自微信团队的提醒。请注意遵守相关规定。
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
                thumbUrl:
                  type: string
                  description: 链接缩略图
                linkUrl:
                  type: string
                  description: 链接地址
                title:
                  type: string
                  description: 链接标题
                description:
                  type: string
                  description: 链接描述
              x-apifox-orders:
                - appId
                - allowWxIds
                - atWxIds
                - disableWxIds
                - privacy
                - content
                - thumbUrl
                - linkUrl
                - title
                - description
              required:
                - appId
                - description
                - title
                - linkUrl
                - thumbUrl
            example:
              appId: '{{appid}}'
              allowWxIds: []
              atWxIds: []
              disableWxIds: []
              content: fugiat sint
              description: >-
                少建片规维门部好将门身对教实们十。一样八七太度及装电部力议应象好。标备北每备志活向较战同光体他。书从线复几细决并面很值话以上。做地江同般劳百山易率干当育起。把件市政层往响包况队算制发。
              title: 族片物
              linkUrl: >-
                https://mbd.baidu.com/newspage/data/landingsuper?context=%7B%22nid%22%3A%22news_9648993262816279801%22%7D&n_type=-1&p_from=-1
              thumbUrl: >-
                https://pics7.baidu.com/feed/a1ec08fa513d269708aaf6569302e2f64216d843.jpeg@f_auto?token=6e5f324904b76e282b92e6c480b80cda
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
              example:
                ret: 200
                msg: 操作成功
                data:
                  id: 14292804688606990000
                  userName: VideosAPi
                  nickName: 苏生
                  createTime: 1703835092
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/朋友圈模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454762-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
