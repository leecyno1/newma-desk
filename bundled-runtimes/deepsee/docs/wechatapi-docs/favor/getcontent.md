# 获取收藏夹内容

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /favor/getContent:
    post:
      summary: 获取收藏夹内容
      deprecated: false
      description: ''
      tags:
        - 核心 API 模块/收藏夹模块
        - 基础API/收藏夹模块
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
                favId:
                  type: integer
                  description: 收藏夹ID
              x-apifox-orders:
                - appId
                - favId
              required:
                - appId
                - favId
            example:
              appId: '{{appid}}'
              favId: 179
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
                      favId:
                        type: integer
                        description: 收藏夹ID
                      status:
                        type: integer
                        description: 状态
                      flag:
                        type: integer
                        description: 收藏夹标识
                      updateTime:
                        type: integer
                        description: 更新时间
                      content:
                        type: string
                        description: 收藏的内容
                    required:
                      - favId
                      - status
                      - flag
                      - updateTime
                      - content
                    x-apifox-orders:
                      - favId
                      - status
                      - flag
                      - updateTime
                      - content
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
                  favId: 179
                  status: 0
                  flag: 0
                  updateTime: 1703235210
                  content: >-
                    <favitem type="1"><desc>没说呢</desc><source
                    sourceid="1838546569535807562"
                    sourcetype="21"><createtime>1703217521</createtime><tousr>wxid_cy6buf12nf6921</tousr><fromusr>zhangchuan2288</fromusr><msgid>1838546569535807562</msgid></source><ctrlflag>127</ctrlflag><taglist></taglist><tagidlist></tagidlist></favitem>
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/收藏夹模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454781-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
