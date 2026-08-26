# 某条朋友圈详情

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /sns/snsDetails:
    post:
      summary: 某条朋友圈详情
      deprecated: false
      description: ''
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
                snsId:
                  type: number
                  description: 朋友圈ID
              x-apifox-orders:
                - appId
                - snsId
              required:
                - appId
                - snsId
            example:
              appId: '{{appid}}'
              snsId: 14214000407987818000
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
                      snsXml:
                        type: string
                        description: 朋友圈的xml，可用于转发朋友圈
                      likeCount:
                        type: integer
                        description: 点赞数
                      likeList:
                        type: array
                        items:
                          type: object
                          properties:
                            userName:
                              type: string
                              description: 点赞好友的wxid
                            nickName:
                              type: string
                              description: 点赞好友的昵称
                            source:
                              type: integer
                              description: 来源
                            type:
                              type: integer
                              description: 类型
                            createTime:
                              type: integer
                              description: 点赞时间
                          required:
                            - userName
                            - nickName
                            - source
                            - type
                            - createTime
                          x-apifox-orders:
                            - userName
                            - nickName
                            - source
                            - type
                            - createTime
                        description: 点赞好友的信息
                      commentCount:
                        type: integer
                        description: 评论数
                      commentList:
                        type: array
                        items:
                          type: object
                          properties:
                            userName:
                              type: string
                              description: 评论好友的wxid
                            nickName:
                              type: string
                              description: 评论好友的昵称
                            source:
                              type: integer
                              description: 来源
                            type:
                              type: integer
                              description: 类型
                            content:
                              type: string
                              description: 评论内容
                            createTime:
                              type: integer
                              description: 评论时间
                            commentId:
                              type: integer
                              description: 评论ID
                            replyCommentId:
                              type: integer
                              description: 回复的评论ID
                            isNotRichText:
                              type: integer
                          required:
                            - userName
                            - nickName
                            - source
                            - type
                            - content
                            - createTime
                            - commentId
                            - replyCommentId
                            - isNotRichText
                          x-apifox-orders:
                            - userName
                            - nickName
                            - source
                            - type
                            - content
                            - createTime
                            - commentId
                            - replyCommentId
                            - isNotRichText
                        description: 评论的内容
                      withUserCount:
                        type: integer
                        description: 提醒谁看的数量
                      withUserList:
                        type: 'null'
                        description: 提醒谁看的wxid
                    required:
                      - id
                      - userName
                      - nickName
                      - createTime
                      - snsXml
                      - likeCount
                      - likeList
                      - commentCount
                      - commentList
                      - withUserCount
                      - withUserList
                    x-apifox-orders:
                      - id
                      - userName
                      - nickName
                      - createTime
                      - snsXml
                      - likeCount
                      - likeList
                      - commentCount
                      - commentList
                      - withUserCount
                      - withUserList
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
                  id: 14214000407987818000
                  userName: VideosApi
                  nickName: VideosApi
                  createTime: 1694440890
                  snsXml: >-
                    <TimelineObject><id>14214000407987819068</id><username>zhangchuan2288</username><createTime>1694440890</createTime><cont">http://shmmsns.qpic.cn/mmsns/FzeKA69P5uIdqPfQxp59LpevPpX0bJz1zbXSpiavc01kia9H4cic0dJbHbUEJDibB8jx2oXfnBuKhgg/0</url><thumb
                    type="1">http://shmmsns.qpic.cn/mmsns/FzeKA69P5uIdqPfQxp59LpevPpX0bJsageAction></messageAction></appMsg></actionInfo><location
                    poiClassifyId="" poiName="" poiAddress=""
                    poiClassifyType="0"
                    city=""></location><publicUserName></publicUserName><streamvideo><streamvideourl></streamvideourl><streamvideothumburl></streamvideothumburl><streamvideoweburl></streamvideoweburl></streamvideo></TimelineObject>
                  likeCount: 4
                  likeList:
                    - userName: '***********'
                      nickName: 糖果
                      source: 0
                      type: 1
                      createTime: 1694440920
                    - userName: '***********'
                      nickName: 挽风～
                      source: 0
                      type: 1
                      createTime: 1694441103
                    - userName: '***********'
                      nickName: ^^辻弌^^
                      source: 0
                      type: 1
                      createTime: 1694441218
                    - userName: '***********'
                      nickName: 丶zoū zoú zoǔ zoù 👾
                      source: 0
                      type: 1
                      createTime: 1694455325
                  commentCount: 19
                  commentList:
                    - userName: '***********'
                      nickName: ME
                      source: 0
                      type: 2
                      content: 去医院验伤 索赔
                      createTime: 1694441070
                      commentId: 1
                      replyCommentId: 0
                      isNotRichText: 1
                    - userName: '***********'
                      nickName: 故事的小黄花
                      source: 0
                      type: 2
                      content: 懂车帝没下载好？
                      createTime: 1694441111
                      commentId: 33
                      replyCommentId: 0
                      isNotRichText: 1
                    - userName: '***********'
                      nickName: 朝夕。
                      source: 0
                      type: 2
                      content: 来不及了，赔了点钱就让走了[捂脸]
                      createTime: 1694441270
                      commentId: 65
                      replyCommentId: 1
                      isNotRichText: 1
                    - userName: '***********'
                      nickName: 挽风～
                      source: 0
                      type: 2
                      content: 对方在想:那人竟然没躺地上，感觉他像自己赚了一个亿那么开心[破涕为笑]
                      createTime: 1694441274
                      commentId: 97
                      replyCommentId: 0
                      isNotRichText: 1
                  withUserCount: 0
                  withUserList: null
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/朋友圈模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454768-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
