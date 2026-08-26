# 获取群二维码

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /group/getChatroomQrCode:
    post:
      summary: 获取群二维码
      deprecated: false
      description: |-
        ### 注意
        - 在新设备登录后的1-3天内，无法使用本功能。在此期间，如果尝试进行获取，您将收到来自微信团队的提醒。请注意遵守相关规定。
        - 生成的群二维码图片7天有效
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
              x-apifox-orders:
                - appId
                - chatroomId
              required:
                - appId
                - chatroomId
            example:
              appId: '{{appid}}'
              chatroomId: '**********@chatroom'
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
                      qrBase64:
                        type: string
                        description: 群二维码图片的base64
                      qrTips:
                        type: string
                        description: 群二维码的提示
                    required:
                      - qrBase64
                      - qrTips
                    x-apifox-orders:
                      - qrBase64
                      - qrTips
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
                  qrBase64: >-
                    /9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAMCAgMCAgMDAwMEAwMEBQgFBQQEBQoHBwYIDAoMDAsKCwsNDhIQDQ4RDgsLEBYQERMUFRUVDA8XGBYUGBIUFRT/wAALCAG4AbgBAREA/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/9oACAEBAAA/AP1Tooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooooor+Veiiiiiiv6qK/lXr+qiiiv5V6/qor+Vev6qKKKKK/lXoooooor+qiiiv5V6KK/qoor+Veiv6qKKK/lXr+qiv5V6KKKKKK/qoooooor+Vev6qKKKKK/lXr+qiiiv5V6KKKKKK/qor+Veiiiv6qKK/lXor+qiiv5V6K/qoor+Veiv6qKK/lXr+qiv5V6KK/qor+Vev6qKKKKK/lXr+qiiiiiiv5V6/qor+Veiiv6qK/lXr+qiiv5V6K/qoor+Veiiv6qK/lXor+qiv5V6/qoor+Veiv6qK/lXor+qiiv5V6/qor+Veiv6qKKKKK/lXor+qiv5V6/qor+Veiiv6qK/lXr+qiiiiiiv5V6/qor+Veiiv6qK/lXr+qiiv5V6K/qor+Veiiiv6qKK/lXor+qiiv5V6/qor+Veiiiv6qKK/lXr+qiiiiv5V6KK/qor+Vev6qKK/lXr+qiv5V6KK/qor+Vev6qKKKKKK/lXr+qiv5V6KK/qor+Vev6qK/lXr+qiiv5V6K/qooor+Veiiiv6qKK/lXoooor+qiv5V6KK/qor+Vev6qKK/lXoor+qiiiiv5V6/qor+Veiiv6qK/lXr+qiiiiiiv5V6/qooooor+Vev6qK/lXr+qiv5V6K/qoor+Vev6qK/lXr+qiiv5V6/qoor+Vev6qKKK/lXoor+qiv5V6KK/qoor+Veiv6qK/lXr+qiiiv5V6/qooooor+Vev6qKKKKKK/lXoooooor+qiv5V6/qor+Vev6qK/lXr+qiv5V6/qor+Vev6qK/lXr+qiv5V6/qor+Vev6qK/lXr+qiv5V6/qor+Vev6qK/lXr+qiv5V6/qor+Vev6qK/lXr+qiv5V6/qor+Vev6qK/lXoooooor+qiiiiiiiiiiiiiiiiiiiv5V6/qor+Veiiiv6qKKK/lXr+qiiiv5V6/qor+Veiv6qK/lXr+qiv5V6/qor+Veiv6qK/lXor+qiiiiiiiiiiiiiiiiv5V6KKKKKK/qor+Veiiv6qK/lXooooooor+qiv5V6KKKK/qoooooor+Veiv6qK/lXor+qiv5V6/qooor+Veiv6qKKK/lXr+qiiiiiiv5V6KKK/qor+Vev6qK/lXr+qiiv5V6/qor+Vev6qK/lXoor+qiv5V6K/qor+Veiiv6qKKK/lXr+qiv5V6KK/qooor+Veiiv6qKKK/lXor+qiiv5V6/qooooooooor+Vev6qK/lXoor+qiv5V6/qor+Veiiv6qKKK/lXoor+qiiiv5V6KKK/qor+Veiiv6qKK/lXr+qiiv5V6/qoor+Veiv6qKK/lXor+qiv5V6/qor+Veiiiv6qKKKKKKK/lXoor+qiv5V6/qooor+Vev6qKKKK/lXoor+qiiv5V6/qooooor+Vev6qKK/lXr+qiiv5V6/qoor+Veiiv6qKKK/lXooor+qiiiv5V6/qooooooor+Vev6qK/lXr+qiiv5V6K/qor+Vev6qK/lXoor+qiv5V6K/qor+Vev6qKKKK/lXr+qiiv5V6K/qor+Vev6qK/lXor+qiiv5V6KKK/qor+Veiv6qK/lXor+qiiiiv5V6/qoooooor+Vev6qK/lXoor+qiiiv5V6K/qor+Vev6qKKKK/lXor+qiiiiv5V6KKK/qooor+Veiv6qKKKKK/lXor+qiv5V6/qoor+Vev6qKKK/lXr+qiiiiiiiiv5V6K/qor+Vev6qK/lXoor+qiv5V6K/qor+Vev6qKKK/lXr+qiiv5V6/qor+Veiv6qK/lXoor+qiv5V6/qooooor+Veiiv6qKK/lXoor+qiiv5V6KKKK/qooooooor+Veiiv6qK/lXr+qiv5V6/qoooor+Veiv6qK/lXoor+qiv5V6K/qoor+Vev6qKKK/lXr+qiv5V6/qoooor+Veiiiiiiv6qK/lXr+qiv5V6/qor+Veiiv6qKKKKKK/lXr+qiv5V6/qoor+Veiiiv6qK/lXoooor+qiiv5V6K/qor+Veiiv6qK/lXor+qiiv5V6/qoor+Vev6qK/lXooor+qiv5V6/qoor+Veiv6qKK/lXr+qiiiiiiiiiv5V6/qooor+Vev6qKK/lXr+qiiiiv5V6K/qoor+Vev6qKKKKKK/lXr+qiiiiiv5V6/qoor+Vev6qK/lXr+qiv5V6KKK/qoor+Veiv6qK/lXor+qiiiiiiiiiv5V6/qor+Vev6qK/lXoor+qiiiv5V6K/qooooor+Veiiiiv6qK/lXor+qiiv5V6/qor+Vev6qKK/lXr+qiiiiiiiv5V6KKKK/qor+Veiv6qKKKKKKK/lXr+qiiv5V6/qooor+Vev6qK/lXr+qiv5V6/qor+Veiiiv6qK/lXoor+qiiv5V6K/qoor+Veiv6qK/lXoooor+qiv5V6KK/qoor+Veiiv6qKKKKKKKKKKKKKKK/lXoor+qiv5V6/qor+Vev6qKKKKKK/lXor+qiiv5V6K/qor+Vev6qKK/lXr+qiiv5V6/qoooor+Veiiiiv6qK/lXor+qiiv5V6K/qooooooooor+Vev6qK/lXor+qiiv5V6/qoor+Veiiv6qK/lXoor+qiv5V6KKK/qooor+Veiiiiv6qK/lXr+qiiv5V6K/qoooor+Veiv6qKK/lXr+qiiiiiiiiiv5V6KK/qor+Veiiiiiv6qKK/lXor+qiv5V6KKKK/qor+Veiiiiiv6qKK/lXr+qiv5V6/qoor+Vev6qKKK/lXr+qiv5V6KKKK/qor+Veiiv6qKKKKKKKK/lXoor+qiiiv5V6/qoor+Vev6qK/lXor+qiiiv5V6/qor+Vev6qK/lXr+qiiiv5V6/qooor+Vev6qKK/lXr+qiiv5V6/qoor+Veiv6qKKK/lXr+qiiiv5V6/qoooooooooor+Vev6qK/lXr+qiv5V6K/qoor+Veiv6qK/lXr+qiiv5V6/qoor+Veiv6qK/lXr+qiv5V6K/qor+Veiiv6qKKK/lXoor+qiiv5V6/qor+Vev6qK/lXoor+qiiiiiiiiiiiiv5V6/qooor+Veiiiv6qKKK/lXr+qiiv5V6KKKK/qooor+Vev6qKK/lXor+qiv5V6/qoor+Veiiv6qKK/lXr+qiiiv5V6KKKK/qooooooor+Veiiiiiiiiiv6qKK/lXr+qiv5V6/qor+Vev6qK/lXr+qiv5V6KKKKKK/qoor+Vev6qK/lXor+qiiiv5V6/qoor+Veiiiiiiv6qK/lXr+qiiiiiiv5V6/qooor+Veiv6qK/lXoor+qiv5V6/qor+Veiv6qKK/lXoor+qiv5V6/qor+Vev6qK/lXoor+qiiiiv5V6K/qooor+Veiv6qK/lXor+qiv5V6/qor+Vev6qK/lXor+qiiiiiiv5V6K/qor+Veiiiiv6qK/lXor+qiiiiv5V6K/qoor+Veiiiv6qK/lXor+qiiv5V6KKK/qor+Vev6qK/lXoor+qiv5V6KK/qoooor+Vev6qK/lXr+qiiiiiiv5V6KK/qoooor+Veiiv6qKK/lXoor+qiv5V6KKK/qooor+Vev6qKK/lXooooor+qiv5V6/qor+Vev6qK/lXr+qiiiv5V6/qor+Veiiv6qK/lXr+qiiiiiiiiiiiv5V6KKK/qor+Vev6qKKK/lXr+qiiv5V6/qooooor+Vev6qKK/lXor+qiv5V6K/qoor+Vev6qK/lXoooooooor+qiv5V6KK/qor+Vev6qKKKKKK/lXr+qiv5V6/qor+Veiv6qKKK/lXor+qiv5V6/qor+Veiv6qKK/lXr+qiv5V6KK/qoor+Veiiv6qK/lXr+qiiiiv5V6/qor+Vev6qKK/lXor+qiiv5V6K/qooooooooooooor+Vev6qK/lXor+qiiiiv5V6K/qor+Veiv6qKKK/lXr+qiiv5V6K/qoor+Vev6qK/lXooooooor+qiv5V6/qor+Veiiiiiiiiv6qKKKKKKKK/lXr+qiiiv5V6/qor+Veiiv6qK/lXr+qiv5V6/qoor+Vev6qKK/lXr+qiv5V6K/qor+Vev6qKK/lXooor+qiv5V6/qoooor+Vev6qKK/lXr+qiiv5V6/qooor+Vev6qKKKKKKKK/lXoor+qiv5V6KKKK/qor+Vev6qK/lXr+qiiiiiiv5V6KK/qooooor+Vev6qKK/lXoooor+qiiiiiv5V6K/qor+Veiv6qKK/lXr+qiiiiiiiv5V6KKK/qooooor+Vev6qK/lXr+qiv5V6KK/qooooor+Veiv6qK/lXr+qiv5V6/qor+Vev6qK/lXor+qiiiv5V6K/qooooor+Veiv6qKKKKKKKKKK/lXor+qiv5V6K/qor+Vev6qK/lXr+qiiiv5V6K/qor+Vev6qKKK/lXor+qiv5V6/qor+Vev6qKK/lXr+qiv5V6KK/qooor+Veiv6qK/lXoor+qiiv5V6/qor+Veiiv6qKKKKKKKKK/lXr+qiv5V6K/qor+Vev6qK/lXr+qiiiv5V6/qoooor+Veiv6qKK/lXr+qiiv5V6K/qoor+Veiv6qK/lXr+qiiv5V6KK/qoor+Vev6qKK/lXr+qiv5V6/qor+Vev6qKKKKKKKK/lXr+qiiiv5V6KK/qor+Vev6qK/lXoooor+qiiiiiv5V6K/qooor+Veiiv6qKK/lXr+qiiiiv5V6KKKKKKKK/qooor+Vev6qKKKKKKK/lXoor+qiiiv5V6KK/qooor+Vev6qKKK/lXoor+qiiiiiv5V6KKK/qor+Veiiiv6qK/lXr+qiiiiiv5V6/qor+Vev6qK/lXr+qiv5V6K/qoooooor+Veiiv6qKKK/lXor+qiv5V6K/qor+Vev6qKK/lXooor+qiiv5V6KKKKK/qoor+Veiv6qKKKK/lXoor+qiv5V6KKKKK/qooor+Vev6qKKKKKKKKKKKKKK/lXor+qiv5V6/qoor+Veiiiv6qKK/lXoor+qiiiv5V6K/qoor+Veiiiv6qK/lXor+qiiiv5V6/qooor+Vev6qKKKKKKKKKK/lXoooooor+qiv5V6/qoor+Vev6qK/lXor+qiiv5V6KKKKK/qor+Vev6qK/lXoooor+qiv5V6/qoor+Vev6qK/lXr+qiiv5V6/qor+Vev6qK/lXor+qiiv5V6/qoooooor+Vev6qKKKKK/lXr+qiv5V6/qooor+Vev6qKK/lXor+qiv5V6/qooor+Vev6qKKK/lXor+qiiv5V6/qor+Veiiiiiiiiv6qKKK/lXr+qiiv5V6K/qoooooor+Vev6qK/lXoor+qiv5V6/qor+Vev6qK/lXooor+qiv5V6/qor+Veiv6qKKK/lXoooor+qiiv5V6KK/qor+Vev6qK/lXooooooooor+qiv5V6/qor+Vev6qKKKKKK/lXr+qiv5V6KK/qor+Vev6qK/lXor+qiv5V6/qoooooor+Veiv6qK/lXor+qiiiiiv5V6KK/qor+Vev6qKK/lXr+qiv5V6/qor+Vev6qK/lXor+qiv5V6/qor+Veiiv6qKKKKKK/lXr+qiv5V6KK/qor+Vev6qK/lXr+qiv5V6KKKKKKK/qoor+Veiv6qK/lXor+qiv5V6K/qor+Vev6qKKK/lXor+qiv5V6KK/qor+Veiv6qK/lXr+qiiv5V6KK/qoooooor+Vev6qKKKKK/lXr+qiv5V6K/qoor+Vev6qKK/lXoor+qiv5V6K/qor+Vev6qKKKK/lXr+qiv5V6/qoor+Veiv6qK/lXor+qiiv5V6K/qor+Vev6qK/lXr+qiiiv5V6/qoooooor+Veiiiiiiv6qKK/lXr+qiiv5V6KK/qooor+Vev6qKK/lXoor+qiv5V6K/qoooor+Vev6qKKK/lXoor+qiiv5V6/qoooor+Veiiiv6qKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKK//2Q==
                  qrTips: 该二维码7天内(1月5日前)有效，重新进入将更新
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/群管理接口
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454725-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
