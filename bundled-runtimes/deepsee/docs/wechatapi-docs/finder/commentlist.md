# 视频-评论列表

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /finder/commentList:
    post:
      summary: 视频-评论列表
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
                  description: 视频号ID
                lastBuffer:
                  type: string
                  description: 首次传空，后续传接口返回的lastBuffer
                sessionBuffer:
                  type: string
                  description: 视频号的sessionBuffer
                objectNonceId:
                  type: string
                  description: 视频号的objectNonceId
                refCommentId:
                  type: integer
                  description: 获取评论回复时传
                rootCommentId:
                  type: integer
                  description: 获取评论回复时传
              required:
                - appId
                - sessionBuffer
                - objectId
                - objectNonceId
              x-apifox-orders:
                - appId
                - objectId
                - lastBuffer
                - sessionBuffer
                - objectNonceId
                - refCommentId
                - rootCommentId
            example:
              appId: '{{appid}}'
              useProxy: true
              rootCommentId: 0
              refCommentId: 0
              objectNonceId: '2423148992597561665_0_0_2_2_1720779660780374'
              sessionBuffer: >-
                eyJyZWNhbGxfdHlwZXMiOltdLCJkZWxpdmVyeV9zY2VuZSI6MiwiZGVsaXZlcnlfdGltZSI6MTcyMDc3OTY2MSwic2V0X2NvbmRpdGlvbl9mbGFnIjo5LCJyZWNhbGxfaW5kZXgiOltdLCJyZXF1ZXN0X2lkIjoxNzIwNzc5NjYwNzgwMzc0LCJtZWRpYV90eXBlIjo0LCJjcmVhdGVfdGltZSI6MTcxNDM4NDcxNywicmVjYWxsX2luZm8iOltdLCJzZWNyZXRlX2RhdGEiOiJCZ0FBNWdBaHQ0K1BkSUtWTExtR0FDUjEwdmg1TGlYdjRrNEpZV3M0VFgzaEMxTFR1ZVJIOFwvdWxybHYyb1JpTHZxYlwvT0F4XC9nSjQ9Iiwib2ZsYWciOjUwMzk3MjAwLCJpZGMiOjMsImRldmljZV90eXBlX2lkIjoxMywiZGV2aWNlX3BsYXRmb3JtIjoiaVBhZDExLDMiLCJmZWVkX3BvcyI6MCwiY2xpZW50X3JlcG9ydF9idWZmIjoie1wiaWZfc3BsaXRfc2NyZWVuX2lwYWRcIjowLFwiZW50ZXJTb3VyY2VJbmZvXCI6XCJ7XFxcImZpbmRlcnVzZXJuYW1lXFxcIjpcXFwiXFxcIixcXFwiZmVlZGlkXFxcIjpcXFwiXFxcIn1cIixcImV4dHJhaW5mb1wiOlwie1xcXCJyZWdjb3VudHJ5XFxcIjpcXFwiQ05cXFwifVwiLFwic2Vzc2lvbklkXCI6XCJTcGxpdFZpZXdFbXB0eVZpZXdDb250cm9sbGVyXzE3MjA3NzkzMzcyMTUjJDBfMTcyMDc3OTMyNDU3OSNcIixcImp1bXBJZFwiOntcInRyYWNlaWRcIjpcIlwiLFwic291cmNlaWRcIjpcIlwifX0iLCJvYmplY3RfaWQiOjE0MzgxMzAxMzUyNTQwNjA4NzkyLCJmaW5kZXJfdWluIjoxMzEwNDgwNDY3NjIwMTIxMSwiZ2VvaGFzaCI6MzM3NzY5OTcyMDUyNzg3MiwiZW50cmFuY2Vfc2NlbmUiOjIsImNhcmRfdHlwZSI6MywiZXhwdF9mbGFnIjo4ODc4Nzk1NSwidXNlcl9tb2RlbF9mbGFnIjo4LCJjdHhfaWQiOiIyLTMtMzItMjk3ZTlhZDRlOTI0MTk2NmM1OTYwYmZhNzc3NmYyNzAxNzIwNzc5MzQyMzQxIiwiZXJpbCI6W10sInBna2V5cyI6W10sInNjaWQiOiI2ZmFlMjE1Yy00MDM4LTExZWYtYjMzMy03ZDdjNzdhYzc4ZTUiLCJjb21tZW50X3ZlciI6MTcxNTQ2OTk4Nn0=
              lastBuffer: ''
              objectId: '14381301352540608792'
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
                      lastBuffer:
                        type: string
                        description: 翻页标识，请求翻页用到
                      commentInfo:
                        type: array
                        items:
                          type: object
                          properties:
                            username:
                              type: string
                              description: 评论方username
                            nickname:
                              type: string
                              description: 昵称
                            content:
                              type: string
                              description: 评论内容
                            commentId:
                              type: integer
                              description: 评论ID
                            replyCommentId:
                              type: integer
                              description: 回复评论ID
                            headUrl:
                              type: string
                              description: 头像
                            createtime:
                              type: integer
                              description: 评论时间
                            likeFlag:
                              type: integer
                            likeCount:
                              type: integer
                              description: 点赞数
                            expandCommentCount:
                              type: integer
                              description: 可展开的评论数
                            continueFlag:
                              type: integer
                            displayFlag:
                              type: integer
                            replyContent:
                              type: string
                              description: 回复评论内容
                            upContinueFlag:
                              type: integer
                            extFlag:
                              type: integer
                            authorContact:
                              type: object
                              properties:
                                username:
                                  type: string
                                nickname:
                                  type: string
                                headUrl:
                                  type: string
                              required:
                                - username
                                - nickname
                                - headUrl
                              x-apifox-orders:
                                - username
                                - nickname
                                - headUrl
                            contentType:
                              type: integer
                              description: 评论类型
                            reportJson:
                              type: string
                            ipRegionInfo:
                              type: object
                              properties:
                                regionText:
                                  type: array
                                  items:
                                    type: string
                              required:
                                - regionText
                              x-apifox-orders:
                                - regionText
                              description: 地区信息
                            levelTwoComment:
                              type: array
                              items:
                                type: string
                          required:
                            - username
                            - nickname
                            - content
                            - commentId
                            - replyCommentId
                            - headUrl
                            - createtime
                            - likeFlag
                            - likeCount
                            - expandCommentCount
                            - continueFlag
                            - displayFlag
                            - replyContent
                            - upContinueFlag
                            - authorContact
                            - contentType
                            - reportJson
                            - ipRegionInfo
                          x-apifox-orders:
                            - username
                            - nickname
                            - content
                            - commentId
                            - replyCommentId
                            - headUrl
                            - createtime
                            - likeFlag
                            - likeCount
                            - expandCommentCount
                            - continueFlag
                            - displayFlag
                            - replyContent
                            - upContinueFlag
                            - extFlag
                            - authorContact
                            - contentType
                            - reportJson
                            - ipRegionInfo
                            - levelTwoComment
                      countInfo:
                        type: object
                        properties:
                          commentCount:
                            type: integer
                            description: 评论数量
                          likeCount:
                            type: integer
                            description: 点赞数量
                          forwardCount:
                            type: integer
                            description: 转发数量
                          favCount:
                            type: integer
                            description: 收藏数量
                        required:
                          - commentCount
                          - likeCount
                          - forwardCount
                          - favCount
                        x-apifox-orders:
                          - commentCount
                          - likeCount
                          - forwardCount
                          - favCount
                      upContinueFlag:
                        type: integer
                      downContinueFlag:
                        type: integer
                      monotonicData:
                        type: object
                        properties:
                          countInfo:
                            type: object
                            properties:
                              commentCount:
                                type: integer
                              likeCount:
                                type: integer
                              forwardCount:
                                type: integer
                              favCount:
                                type: integer
                            required:
                              - commentCount
                              - likeCount
                              - forwardCount
                              - favCount
                            x-apifox-orders:
                              - commentCount
                              - likeCount
                              - forwardCount
                              - favCount
                          commentCount:
                            type: object
                            properties:
                              commentCount:
                                type: integer
                            required:
                              - commentCount
                            x-apifox-orders:
                              - commentCount
                        required:
                          - countInfo
                          - commentCount
                        x-apifox-orders:
                          - countInfo
                          - commentCount
                    required:
                      - commentInfo
                      - countInfo
                      - lastBuffer
                      - upContinueFlag
                      - downContinueFlag
                      - monotonicData
                    x-apifox-orders:
                      - lastBuffer
                      - commentInfo
                      - countInfo
                      - upContinueFlag
                      - downContinueFlag
                      - monotonicData
                required:
                  - ret
                  - msg
                  - data
                x-apifox-orders:
                  - ret
                  - msg
                  - data
              example: "{\n    \"ret\": 200,\n    \"msg\": \"操作成功\",\n    \"data\": {\n        \"commentInfo\": [\n            {\n                \"username\": \"v2_060000231003b20faec8c6e18f10c7d6c903ec3db0776955d3d97c6b329d6aa58693bcdb7ad1@finder\",\n                \"nickname\": \"朝夕v\",\n                \"content\": \"。。\",\n                \"commentId\": 14305741204655704125,\n                \"replyCommentId\": 0,\n                \"headUrl\": \"http://wx.qlogo.cn/finderhead/Q3auHgzwzM5grqOsJtnHiaiapZ4cv43GNBTMaIUC7mVSGhKAPVyfY17w/0\",\n                \"createtime\": 1705377245,\n                \"likeFlag\": 0,\n                \"likeCount\": 0,\n                \"expandCommentCount\": 0,\n                \"continueFlag\": 0,\n                \"displayFlag\": 2,\n                \"replyContent\": \"\",\n                \"upContinueFlag\": 0,\n                \"extFlag\": 2,\n                \"authorContact\": {\n                    \"username\": \"v2_060000231003b20faec8c6e18f10c7d6c903ec3db0776955d3d97c6b329d6aa58693bcdb7ad1@finder\",\n                    \"nickname\": \"朝夕v\",\n                    \"headUrl\": \"http://wx.qlogo.cn/finderhead/Q3auHgzwzM5grqOsJtnHiaiapZ4cv43GNBTMaIUC7mVSGhKAPVyfY17w/0\"\n                },\n                \"contentType\": 0,\n                \"reportJson\": \"{}\",\n                \"ipRegionInfo\": {\n                    \"regionText\": [\n                        \"江苏\"\n                    ]\n                }\n            },\n            {\n                \"username\": \"v5_020b0a166104010000000000ed5c075b5fe340000000b1afa7d8728e3dd43ef4317a780e33c2de646dc7a8e59366e1f748ba6d9fc09714e897e44b9e9b517892fc49168b6e38b5c0352e519c26c4f368f3fd37@stranger\",\n                \"nickname\": \"朝夕。\",\n                \"content\": \"评论内容\",\n                \"commentId\": 14305150019061090364,\n                \"replyCommentId\": 0,\n                \"headUrl\": \"https://wx.qlogo.cn/mmhead/ver_1/lkib5XsC6ia74xkuskSe7o96KCtBOCO9lfrtufGn3pFwWclDxhj9enH2YVSUuRKr1zgBBPSndactfvicqURxzhePRIJnlBCPrfyXt3mnHqbrcrOeBH4jlDHwLDL9LRoyKJA/132\",\n                \"createtime\": 1705306770,\n                \"likeFlag\": 0,\n                \"likeCount\": 0,\n                \"expandCommentCount\": 0,\n                \"continueFlag\": 0,\n                \"displayFlag\": 0,\n                \"replyContent\": \"\",\n                \"upContinueFlag\": 0,\n                \"authorContact\": {\n                    \"username\": \"v5_020b0a166104010000000000ed5c075b5fe340000000b1afa7d8728e3dd43ef4317a780e33c2de646dc7a8e59366e1f748ba6d9fc09714e897e44b9e9b517892fc49168b6e38b5c0352e519c26c4f368f3fd37@stranger\",\n                    \"nickname\": \"朝夕。\",\n                    \"headUrl\": \"https://wx.qlogo.cn/mmhead/ver_1/lkib5XsC6ia74xkuskSe7o96KCtBOCO9lfrtufGn3pFwWclDxhj9enH2YVSUuRKr1zgBBPSndactfvicqURxzhePRIJnlBCPrfyXt3mnHqbrcrOeBH4jlDHwLDL9LRoyKJA/132\"\n                },\n                \"contentType\": 0,\n                \"reportJson\": \"{}\",\n                \"ipRegionInfo\": {\n                    \"regionText\": [\n                        \"浙江\"\n                    ]\n                }\n            },\n            {\n                \"username\": \"v5_020b0a166104010000000000ed5c075b5fe340000000b1afa7d8728e3dd43ef4317a780e33c2de646dc7a8e59366e1f748ba6d9fc09714e897e44b9e9b517892fc49168b6e38b5c0352e519c26c4f368f3fd37@stranger\",\n                \"nickname\": \"朝夕。\",\n                \"content\": \"hh\",\n                \"commentId\": 14305098373537073222,\n                \"replyCommentId\": 0,\n                \"headUrl\": \"https://wx.qlogo.cn/mmhead/ver_1/lkib5XsC6ia74xkuskSe7o96KCtBOCO9lfrtufGn3pFwWclDxhj9enH2YVSUuRKr1zgBBPSndactfvicqURxzhePRIJnlBCPrfyXt3mnHqbrcrOeBH4jlDHwLDL9LRoyKJA/132\",\n                \"createtime\": 1705300614,\n                \"likeFlag\": 0,\n                \"likeCount\": 0,\n                \"expandCommentCount\": 0,\n                \"continueFlag\": 0,\n                \"displayFlag\": 0,\n                \"replyContent\": \"\",\n                \"upContinueFlag\": 0,\n                \"authorContact\": {\n                    \"username\": \"v5_020b0a166104010000000000ed5c075b5fe340000000b1afa7d8728e3dd43ef4317a780e33c2de646dc7a8e59366e1f748ba6d9fc09714e897e44b9e9b517892fc49168b6e38b5c0352e519c26c4f368f3fd37@stranger\",\n                    \"nickname\": \"朝夕。\",\n                    \"headUrl\": \"https://wx.qlogo.cn/mmhead/ver_1/lkib5XsC6ia74xkuskSe7o96KCtBOCO9lfrtufGn3pFwWclDxhj9enH2YVSUuRKr1zgBBPSndactfvicqURxzhePRIJnlBCPrfyXt3mnHqbrcrOeBH4jlDHwLDL9LRoyKJA/132\"\n                },\n                \"contentType\": 0,\n                \"reportJson\": \"{}\",\n                \"ipRegionInfo\": {\n                    \"regionText\": [\n                        \"浙江\"\n                    ]\n                }\n            },\n            {\n                \"username\": \"v2_060000231003b20faec8c7ea8f1ecbd1c901ef3cb0773696efb506324185fdd53ba44426a8a7@finder\",\n                \"nickname\": \"阿星5679\",\n                \"content\": \"哈哈\",\n                \"commentId\": 14279589493825607865,\n                \"replyCommentId\": 0,\n                \"headUrl\": \"http://wx.qlogo.cn/finderhead/SQd7RF5caa0TmEbngQTrcibuK8MmrARRSDKxbNrMWiaX7NcuABsSSTUA/0\",\n                \"levelTwoComment\": [\"\\nVv2_060000231003b20faec8c6e18f10c7d6c903ec3db0776955d3d97c6b329d6aa58693bcdb7ad1@finder\x12\a朝夕v\x1A\\b/::D/::D ������ҕ�\x01(������ҕ�\x01:Xhttp://wx.qlogo.cn/finderhead/Q3auHgzwzM5grqOsJtnHiaiapZ4cv43GNBTMaIUC7mVSGhKAPVyfY17w/0H��٫\x06`\0h\0�\x01\x02�\x01\x06哈哈�\x01\x02�\x01�\x01\\nVv2_060000231003b20faec8c6e18f10c7d6c903ec3db0776955d3d97c6b329d6aa58693bcdb7ad1@finder\x12\a朝夕v\x1AXhttp://wx.qlogo.cn/finderhead/Q3auHgzwzM5grqOsJtnHiaiapZ4cv43GNBTMaIUC7mVSGhKAPVyfY17w/0�\x01\0�\x02\x02{}�\x02\\b\\n\x06江苏\"\n                ],\n                \"createtime\": 1702259718,\n                \"likeFlag\": 0,\n                \"likeCount\": 0,\n                \"expandCommentCount\": 1,\n                \"continueFlag\": 0,\n                \"displayFlag\": 520,\n                \"replyContent\": \"\",\n                \"upContinueFlag\": 0,\n                \"authorContact\": {\n                    \"username\": \"v2_060000231003b20faec8c7ea8f1ecbd1c901ef3cb0773696efb506324185fdd53ba44426a8a7@finder\",\n                    \"nickname\": \"阿星5679\",\n                    \"headUrl\": \"http://wx.qlogo.cn/finderhead/SQd7RF5caa0TmEbngQTrcibuK8MmrARRSDKxbNrMWiaX7NcuABsSSTUA/0\"\n                },\n                \"contentType\": 0,\n                \"reportJson\": \"{}\",\n                \"ipRegionInfo\": {\n                    \"regionText\": [\n                        \"江苏\"\n                    ]\n                }\n            }\n        ],\n        \"countInfo\": {\n            \"commentCount\": 5,\n            \"likeCount\": 2,\n            \"forwardCount\": 1,\n            \"favCount\": 2\n        },\n        \"lastBuffer\": \"CgsIubGAr8/f0pXGARABCL6SgI/o7Ln/xAEYACC+koCP6Oy5/8QB\",\n        \"upContinueFlag\": 0,\n        \"downContinueFlag\": 0,\n        \"monotonicData\": {\n            \"countInfo\": {\n                \"commentCount\": 5,\n                \"likeCount\": 2,\n                \"forwardCount\": 1,\n                \"favCount\": 2\n            },\n            \"commentCount\": {\n                \"commentCount\": 5\n            }\n        }\n    }\n}"
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/视频号模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454796-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
