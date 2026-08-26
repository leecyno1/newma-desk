# 视频-评论

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /finder/comment:
    post:
      summary: 视频-评论
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
                content:
                  type: string
                  description: 评论内容
                objectId:
                  type: integer
                  description: 视频号的objectId
                sessionBuffer:
                  type: string
                  description: 视频号的sessionBuffer
                objectNonceId:
                  type: string
                  description: 视频号的objectNonceId
                opType:
                  type: integer
                  description: 0评论 1删除评论
                myUserName:
                  type: string
                  description: 自己的username
                myRoleType:
                  type: integer
                  description: 自己的roletype
                replyUserName:
                  type: string
                  description: 回复评论的username
                refCommentId:
                  type: string
                  description: 回复评论时传
                rootCommentId:
                  type: string
                  description: 回复评论时传
                commentId:
                  type: integer
                  description: 评论ID，删除评论时传
              required:
                - appId
                - myUserName
                - opType
                - sessionBuffer
                - objectId
                - myRoleType
                - content
                - commentId
              x-apifox-orders:
                - appId
                - content
                - commentId
                - objectId
                - sessionBuffer
                - objectNonceId
                - opType
                - myUserName
                - myRoleType
                - replyUserName
                - refCommentId
                - rootCommentId
            example:
              appId: '{{appid}}'
              useProxy: true
              myUserName: >-
                v2_060000231003b20faec8c7e28811c4d5cc0ded37b0779c48c759a7446a87688c2774e5300c32@finder
              opType: 0
              objectNonceId: '16628169456191691547_0_39_2_1_0'
              sessionBuffer: >-
                eyJjdXJfbGlrZV9jb3VudCI6MiwiY3VyX2NvbW1lbnRfY291bnQiOjUsInJlY2FsbF90eXBlcyI6W10sImRlbGl2ZXJ5X3NjZW5lIjoyLCJkZWxpdmVyeV90aW1lIjoxNzA2MDg2ODE2LCJzZXRfY29uZGl0aW9uX2ZsYWciOjksImZyaWVuZF9jb21tZW50X2luZm8iOnsibGFzdF9mcmllbmRfdXNlcm5hbWUiOiJ6aGFuZ2NodWFuMjI4OCIsImxhc3RfZnJpZW5kX2xpa2VfdGltZSI6MTcwMzcyNjI4OH0sInRvdGFsX2ZyaWVuZF9saWtlX2NvdW50IjoxLCJyZWNhbGxfaW5kZXgiOltdLCJtZWRpYV90eXBlIjoyLCJjcmVhdGVfdGltZSI6MTY5MjE4MDMzNSwicmVjYWxsX2luZm8iOltdLCJvZmxhZyI6NDA5NzYsImlkYyI6MSwiZGV2aWNlX3R5cGVfaWQiOjEzLCJkZXZpY2VfcGxhdGZvcm0iOiJpUGFkMTMsNyIsImZlZWRfcG9zIjowLCJjbGllbnRfcmVwb3J0X2J1ZmYiOiJ7XCJpZl9zcGxpdF9zY3JlZW5faXBhZFwiOjAsXCJlbnRlclNvdXJjZUluZm9cIjpcIntcXFwiZmluZGVydXNlcm5hbWVcXFwiOlxcXCJcXFwiLFxcXCJmZWVkaWRcXFwiOlxcXCJcXFwifVwiLFwiZXh0cmFpbmZvXCI6XCJ7XFxuIFxcXCJyZWdjb3VudHJ5XFxcIiA6IFxcXCJDTlxcXCJcXG59XCIsXCJzZXNzaW9uSWRcIjpcIjEwMV8xNzA2MDg2ODA1NTE3IyQwXzE3MDYwODY3OTI4ODEjXCIsXCJqdW1wSWRcIjp7XCJ0cmFjZWlkXCI6XCJcIixcInNvdXJjZWlkXCI6XCJcIn19IiwiY29tbWVudF9zY2VuZSI6MzksIm9iamVjdF9pZCI6MTQxOTUwMzc1MDI5NzAwMDU4MjIsImZpbmRlcl91aW4iOjEzMTA0ODA0MjY5NDM3NzA5LCJnZW9oYXNoIjozMzc3Njk5NzIwNTI3ODcyLCJlbnRyYW5jZV9zY2VuZSI6MSwiY2FyZF90eXBlIjoxLCJleHB0X2ZsYWciOjMwMDY3Njk5LCJ1c2VyX21vZGVsX2ZsYWciOjgsImlzX2ZyaWVuZCI6dHJ1ZSwiY3R4X2lkIjoiMS0xLTIwLWJmNmEyNzQzYzhiNTM1ZjJlNmY2MzEyZjUwZjM3M2VjMTcwNjA4NjgxMDY0MyIsImFkX2ZsYWciOjQsImVyaWwiOltdLCJwZ2tleXMiOltdLCJzY2lkIjoiZmRiMjg0MGMtYmE5Ni0xMWVlLTg0MDAtZGI5NzlkZmJlZTYwIn0=
              objectId: 14195037502970006000
              myRoleType: 3
              content: 评论内容
              commentId: 0
              replyUserName: ''
              refCommentId: 0
              rootCommentId: 0
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
                      commentId:
                        type: 'null'
                        description: 评论ID
                    required:
                      - commentId
                    x-apifox-orders:
                      - commentId
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
                  commentId: null
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/视频号模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454799-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
