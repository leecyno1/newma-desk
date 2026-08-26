# 发送定位置消息

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /message/postLocation:
    post:
      summary: 发送定位置消息
      deprecated: false
      description: |-
        本接口为发送/转发定位消息，使用回调中XML数据
        可保存结构，修改经度纬度，label，poiname
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
                content:
                  type: string
                  description: 回调消息中的content节点内容
              x-apifox-orders:
                - appId
                - toWxid
                - content
              required:
                - appId
                - toWxid
                - content
            example:
              appId: wx_wLCyJbw5J******wvy
              toWxid: wxid_krcc*****hbj22
              content: "<msg>\n\t<location x=\"34.283573\" y=\"117.188789\" scale=\"15\" label=\"鼓楼区南京路\" maptype=\"0\" poiname=\"鼓楼区雨花台(详细地址)\" poiid=\"nearby_792894707970093245\" buildingId=\"\" floorName=\"\" poiCategoryTips=\"\" poiBusinessHour=\"\" poiPhone=\"\" poiPriceTips=\"0.0\" isFromPoiList=\"false\" adcode=\"\" cityname=\"\" />\n</msg>"
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
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/消息模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-373442846-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
