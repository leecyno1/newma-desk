# 视频-小红心

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /finder/idLike:
    post:
      summary: 视频-小红心
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
                objectId:
                  type: integer
                  description: 对方视频号主页的objectId
                sessionBuffer:
                  type: string
                  description: 对方视频号主页的sessionBuffer
                objectNonceId:
                  type: string
                  description: 对方视频号主页的objectNonceId
                opType:
                  type: integer
                  description: 3喜欢  4不喜欢
                myUserName:
                  type: string
                  description: 自己的username
                myRoleType:
                  type: integer
                  description: 自己的roletype，默认为3
                toUserName:
                  type: string
                  description: 对方的username
              required:
                - appId
                - myUserName
                - opType
                - objectNonceId
                - sessionBuffer
                - objectId
                - myRoleType
                - toUserName
              x-apifox-orders:
                - appId
                - myRoleType
                - myUserName
                - toUserName
                - objectId
                - sessionBuffer
                - objectNonceId
                - opType
            example:
              appId: '{{appid}}'
              useProxy: true
              myUserName: >-
                v2_060000231003bc8cae7811bcadcc904ef30b0770fd600f70cfec5c128fc2ef6421e0c7a@finder
              toUserName: >-
                v2_060000231003aec8c6e58e1fc1d5cf06ed35b07774395a04f79f4e39faa121ac3df32ce4@finder
              opType: 3
              objectNonceId: '164696651971598930_0_32_2_2_1734408307116817'
              sessionBuffer: >-
                eyJjdXJfbGlrZV9jb3VudCI6NCwiY3VyX2NvbW1lbnRfY291bnQiOjksInJlY2FsbF90eXBlcyI6W10sImRlbGl2ZXJ5X3NjZW5lIjoyLCJkZWxpdmVyeV90aW1lIjoxNzM0NDA4MzA3LCJzZXRfY29uZGl0aW9uX2ZsYWciOjksInJlY2FsbF9pbmRleCI6W10sInJlcXVlc3RfaWQiOjE3MzQ0MDgzMDcxMTY4MTcsIm1lZGlhX3R5cGUiOjQsInZpZF9sZW4iOjE1LCJjcmVhdGVfdGltZSI6MTcwNTI1ODQxNiwicmVjYWxsX2luZm8iOltdLCJzZWNyZXRlX2RhdGEiOiJCZ0FBUlVkMFd0TGQrUlk1WXhDTGZQTjlZVVMxM0wxNUtaTHpTRE55R0pxSzZuamdLMmlnWUgwXC82bDNVMngzbGNGYTV2TkViR0x3PSIsIm9mbGFnIjozMTg3NzUzMTIsInRhYl9zZXNzaW9uX2lkIjoxNzM0NDA4MzA3MTM5NzE2LCJpZGMiOjEsImRldmljZV90eXBlX2lkIjoxMywiZGV2aWNlX3BsYXRmb3JtIjoiaVBhZDExLDMiLCJmZWVkX3BvcyI6MCwiY2xpZW50X3JlcG9ydF9idWZmIjoie1wiaWZfc3BsaXRfc2NyZWVuX2lwYWRcIjowLFwiZW50ZXJTb3VyY2VJbmZvXCI6XCJ7XFxcImZpbmRlcnVzZXJuYW1lXFxcIjpcXFwiXFxcIixcXFwiZmVlZGlkXFxcIjXFwiXFxcIn1cIixcImV4dHJhaW5mb1wiOlwie1xcXCJyZWdjb3VudHJ5XFxcIjpcXFwiQ05cXFwifVwiLFwic2Vzc2lvbklkXCI6XCJTcGxpdFZpZXdFbXB0eVZpZXdDb250cm9sbGVyXzE3MzQ0MDgyOTg1MzcjJDBfMTczNDQwODI4NTkwMSNcIixcImp1bXBJZFwiOntcInRyYWNlaWRcIjpcIlwiLFwic291cmNlaWRcIjpcIlwifX0iLCJjb21tZW50X3NjZW5lIjozMiwib2JqZWN0X2lkIjoxNDMwNDc0NDM5MTEzNDQ4NDc2MCwiZ2VvaGFzaCI6MzM3NzY5OTcyMDUyNzg3MiwidGFiX2ZlZWRfcG9zIjowLCJlbnRyYW5jZV9zY2VuZSI6MiwiY2FyZF90eXBlIjozLCJleHB0X2ZsYWciOjg4Nzg3OTU1LCJ1c2VyX21vZGVsX2ZsYWciOjgsImN0eF9pZCI6IjItMy0zMi1jMzk1YTljYzNmZjA4MWU1YWRjYjgyZTE1Y2Q0Nzg3MzE3MzQ0MDgzMDM2NjMiLCJvYmpfZmxhZyI6MTA3Mzc0MTgyNCwiZXJpbCI6W10sInBna2V5cyI6W10sInNjaWQiOiIxOWVhYWViNC1iYzJjLTExZWYtODkxMy04OTlmNWU4MGY4NTUiLCJjb21tZW50X3ZlciI6MTczNDIxNzIwMn0=
              objectId: 1430474439113484800
              myRoleType: 3
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
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454798-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
