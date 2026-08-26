# 发送视频消息

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /message/postVideo:
    post:
      summary: 发送视频消息
      deprecated: false
      description: >-
        #### 注意

        发送视频接口会返回cdn相关的信息，如有需求同一个视频发送多次，第二次及以后发送时可使用接口返回的cdn信息拼装xml调用[转发视频接口](http://apifox.videosapi.com/api-170454744)，这样可以缩短发送时间
      tags:
        - 核心 API 模块/消息模块
        - 基础API/消息模块
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
                toWxid:
                  type: string
                  description: 好友/群的ID
                videoUrl:
                  type: string
                  description: 视频的链接
                thumbUrl:
                  type: string
                  description: 缩略图的链接
                videoDuration:
                  type: integer
                  description: 视频的播放时长，单位秒
              x-apifox-orders:
                - appId
                - toWxid
                - videoUrl
                - thumbUrl
                - videoDuration
              required:
                - appId
                - toWxid
                - videoUrl
                - thumbUrl
                - videoDuration
            example:
              appId: '{{appid}}'
              toWxid: '**********@chatroom'
              videoUrl: >-
                https://scrm-1308498490.cos.ap-shanghai.myqcloud.com/pkg/436fa030-18a45a6e917.mp4?q-sign-algorithm=sha1&q-ak=AKIDmOkqfDUUDfqjMincBSSAbleGaeQv96mB&q-sign-time=1703841673;1703848873&q-key-time=1703841673;1703848873&q-header-list=&q-url-param-list=&q-signature=2527904720ee07fd5bfc6cfffa001b415fd08329
              thumbUrl: >-
                https://scrm-1308498490.cos.ap-shanghai.myqcloud.com/pkg/hhh.jpeg?q-sign-algorithm=sha1&q-ak=AKIDmOkqfDUUDfqjMincBSSAbleGaeQv96mB&q-sign-time=1703841885;1703849085&q-key-time=1703841885;1703849085&q-header-list=&q-url-param-list=&q-signature=c0a3837bde236636c342373e19551e332c40d847
              videoDuration: 10
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
                      toWxid:
                        type: string
                        description: 接收人的wxid
                      createTime:
                        type: 'null'
                        description: 发送时间
                      msgId:
                        type: integer
                        description: 消息ID
                      newMsgId:
                        type: integer
                        description: 消息ID
                      type:
                        type: 'null'
                        description: 消息类型
                      aesKey:
                        type: string
                        description: cdn相关的aeskey
                      fileId:
                        type: string
                        description: cdn相关的fileid
                      length:
                        type: integer
                        description: 视频文件大小
                    required:
                      - toWxid
                      - createTime
                      - msgId
                      - newMsgId
                      - type
                      - aesKey
                      - fileId
                      - length
                    x-apifox-orders:
                      - toWxid
                      - createTime
                      - msgId
                      - newMsgId
                      - type
                      - aesKey
                      - fileId
                      - length
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
                  toWxid: '**********@chatroom'
                  createTime: null
                  msgId: 769523567
                  newMsgId: 945590746179451500
                  type: null
                  aesKey: 687a636f627579667a756a7168717968
                  fileId: >-
                    3052020100044b304902010002043904752002033d11ff02045dd79b240204658e9072042466633131376136662d366566632d343638662d613633662d3536316139616133383362350204012400040201000400
                  length: 1315979
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/消息模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454736-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
