# 转发文件

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /message/forwardFile:
    post:
      summary: 转发文件
      deprecated: false
      description: ''
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
                xml:
                  type: string
                  description: 文件消息的xml
              x-apifox-orders:
                - appId
                - toWxid
                - xml
              required:
                - appId
                - toWxid
                - xml
            example:
              appId: '{{appid}}'
              toWxid: '***********@chatroom'
              xml: "<?xml version=\"1.0\"?>\n<msg>\n\t<appmsg appid=\"\" sdkver=\"0\">\n\t\t<title>info.json</title>\n\t\t<des />\n\t\t<action />\n\t\t<type>6</type>\n\t\t<showtype>0</showtype>\n\t\t<soundtype>0</soundtype>\n\t\t<mediatagname />\n\t\t<messageext />\n\t\t<messageaction />\n\t\t<content />\n\t\t<contentattr>0</contentattr>\n\t\t<url />\n\t\t<lowurl />\n\t\t<dataurl />\n\t\t<lowdataurl />\n\t\t<appattach>\n\t\t\t<totallen>63</totallen>\n\t\t\t<attachid>@cdn_3057020100044b304902010002043904752002032f7d6d02046bb5bade02046593760c042433653765306131612d646138622d346662322d383239362d3964343665623766323061370204051400050201000405004c53d900_f46be643aa0dc009ae5fb63bbc73335d_1</attachid>\n\t\t\t<emoticonmd5 />\n\t\t\t<fileext>json</fileext>\n\t\t\t<cdnattachurl>3057020100044b304902010002043904752002032f7d6d02046bb5bade02046593760c042433653765306131612d646138622d346662322d383239362d3964343665623766323061370204051400050201000405004c53d900</cdnattachurl>\n\t\t\t<aeskey>f46be643aa0dc009ae5fb63bbc73335d</aeskey>\n\t\t\t<encryver>0</encryver>\n\t\t\t<overwrite_newmsgid>594239960546299206</overwrite_newmsgid>\n\t\t\t<fileuploadtoken>v1_0bgfyCkUmoZYYyvXys0cCiJdd2R/pKPdD2TNi9IY6FOt+Tvlhp3ijUoupZHzyB2Lp7xYgdVFaUGL4iu3Pm9/YACCt20egPGpT+DKe+VymOzD7tJfsS8YW7JObTbN8eVoFEetU5HSRWTgS/48VVsPZMoDF6Gz1XJDLN/dWRxvzrbOzVGGNvmY4lpXb0kRwXkSxwL+dO4=</fileuploadtoken>\n\t\t</appattach>\n\t\t<extinfo />\n\t\t<sourceusername />\n\t\t<sourcedisplayname />\n\t\t<thumburl />\n\t\t<md5>d16070253eee7173e467dd7237d76f60</md5>\n\t\t<statextstr />\n\t</appmsg>\n\t<fromusername>zhangchuan2288</fromusername>\n\t<scene>0</scene>\n\t<appinfo>\n\t\t<version>1</version>\n\t\t<appname></appname>\n\t</appinfo>\n\t<commenturl></commenturl>\n</msg>"
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
                        type: integer
                        description: 发送时间
                      msgId:
                        type: integer
                        description: 消息ID
                      newMsgId:
                        type: integer
                        description: 消息ID
                      type:
                        type: integer
                        description: 消息类型
                    required:
                      - toWxid
                      - createTime
                      - msgId
                      - newMsgId
                      - type
                    x-apifox-orders:
                      - toWxid
                      - createTime
                      - msgId
                      - newMsgId
                      - type
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
                  toWxid: '***********@chatroom'
                  createTime: 1704162866
                  msgId: 769533740
                  newMsgId: 6455486805605396000
                  type: 6
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/消息模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454742-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
