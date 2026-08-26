# 视频-直接发布视频

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /finder/publishFinderWeb:
    post:
      summary: 视频-直接发布视频
      deprecated: false
      description: ''
      tags:
        - 核心 API 模块/视频号模块
        - 基础API/视频号模块
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
                videoUrl:
                  type: string
                  description: 视频链接地址
                thumbUrl:
                  type: string
                  description: 封面链接地址
                description:
                  type: string
                  description: 视频号描述
                myRoleType:
                  type: integer
                  description: 自己的roletype，默认为3
                title:
                  type: string
                  description: 标题
              required:
                - appId
                - videoUrl
                - thumbUrl
                - description
                - title
              x-apifox-orders:
                - appId
                - title
                - videoUrl
                - thumbUrl
                - description
                - myRoleType
            example:
              appId: '{{appid}}'
              useProxy: true
              title: test测试
              videoUrl: >-
                https://scrm-1308498490.cos.ap-shanghai.myqcloud.com/test/d7c616569ac342ad1fa8e3301682844e.mp4?q-sign-algorithm=sha1&q-ak=AKIDmOkqfDUUDfqjMincBSSAbleGaeQv96mB&q-sign-time=1735795742;10375709342&q-key-time=1735795742;10375709342&q-header-list=&q-url-param-list=&q-signature=10a1f7548fa65c8a20c2958f18b68f0db9dfd13d
              thumbUrl: >-
                https://scrm-1308498490.cos.ap-shanghai.myqcloud.com/test/photo_2024-10-05_12-15-43.jpg?q-sign-algorithm=sha1&q-ak=AKIDmOkqfDUUDfqjMincBSSAbleGaeQv96mB&q-sign-time=1735797655;10375711255&q-key-time=1735797655;10375711255&q-header-list=&q-url-param-list=&q-signature=5f0a4253c08b6d14c018aa1fd9295c129acbb64c
              description: '#测试##123#'
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
              examples:
                '1':
                  summary: 成功示例
                  value:
                    ret: 200
                    msg: 发布成功
                '2':
                  summary: 异常示例
                  value:
                    ret: 500
                    msg: 发布视频失败
                    data:
                      code: '-4013'
                      msg: null
          headers: {}
          x-apifox-name: 成功
        '500':
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
                      code:
                        type: string
                      msg:
                        type: 'null'
                    required:
                      - code
                      - msg
                    x-apifox-orders:
                      - code
                      - msg
                required:
                  - ret
                  - msg
                  - data
                x-apifox-orders:
                  - ret
                  - msg
                  - data
          headers: {}
          x-apifox-name: 服务器错误
      security: []
      x-apifox-folder: 核心 API 模块/视频号模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-255758615-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
