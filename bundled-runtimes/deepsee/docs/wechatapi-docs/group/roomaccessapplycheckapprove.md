# 确认进群申请

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /group/roomAccessApplyCheckApprove:
    post:
      summary: 确认进群申请
      deprecated: false
      description: 群聊开启邀请确认后，有人申请进群时群主和管理员会收到进群申请，本接口用于确认进群申请
      tags:
        - 核心 API 模块/群管理接口
        - 基础API/群模块
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
                chatroomId:
                  type: string
                  description: 群ID
                newMsgId:
                  type: string
                  description: 消息ID
                msgContent:
                  type: string
                  description: 消息内容
              x-apifox-orders:
                - appId
                - chatroomId
                - newMsgId
                - msgContent
              required:
                - appId
                - chatroomId
                - msgContent
                - newMsgId
            example:
              appId: '{{appid}}'
              chatroomId: '**********@chatroom'
              msgContent: "<sysmsg type=\"NewXmlChatRoomAccessVerifyApplication\">\n\t<NewXmlChatRoomAccessVerifyApplication>\n\t\t<text> <![CDATA[\"Ashley\"想邀请1位朋友加入群聊]]></text>\n\t\t <link>\n\t\t\t<scene>roomaccessapplycheck_approve</scene>\n\t\t\t<text> <![CDATA[ 去确认]]></text>\n\t\t\t<ticket> <![CDATA[AwAAAAEAAAAVxQT9t2UOmpKWhJUViezAdSPKcaOLjP8JydTTWGHXiByZInpCp71HDoXAui/u7ByQVOutX93UlKBpkA2/3FoSAET1nA==]]> </ticket>\n\t\t\t<invitationreason> <![CDATA[进一下]]> </invitationreason>\n\t\t\t<inviterusername> <![CDATA[wxid_p**********]]> </inviterusername>\n\t\t\t<memberlist>\n\t\t\t\t<memberlistsize>1</memberlistsize>\n\t\t\t\t<member>\n\t\t\t\t\t<username> <![CDATA[wxid_8pvk**********]]> </username>\n\t\t\t\t\t<nickname> <![CDATA[白开水加糖]]> </nickname>\n\t\t\t\t\t<headimgurl> <![CDATA[http://wx.qlogo.cn/mmhead/ver_1/b6BQ3ibU4I5hDEtSyR1unAOaQMymjgk6gE9bUmteJUY6JAaJeMKJvibkLEia8PpbvuDo96bC5JKhydyLJWia7yTmahwwb0ZfjGZy9jMsibbQBVmU/96]]> </headimgurl>\n\t\t\t\t\t<quitchatroominfo> <![CDATA[曾被移出群聊,建议谨慎通过,]]> </quitchatroominfo>\n\t\t\t\t</member>\n\t\t\t</memberlist>\n\t\t</link>\n\t\t<RoomName> <![CDATA[34757816141@chatroom]]> </RoomName>\n\t</NewXmlChatRoomAccessVerifyApplication>\n</sysmsg>"
              newMsgId: '8866462780395237368'
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
      x-apifox-folder: 核心 API 模块/群管理接口
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454731-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
