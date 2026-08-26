# 修改好友标签

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /label/modifyMemberList:
    post:
      summary: 修改好友标签
      deprecated: false
      description: >-
        #### 注意

        由于好友标签信息存储在用户客户端，因此每次在修改时都需要进行全量修改。举例来说，考虑好友A（wxid_asdfaihp123），该好友已经被标记为标签ID为1和2。


        在添加标签ID为3时，传递的参数如下：labelIds：1,2,3，wxIds：[wxid_asdfaihp123]。这表示要给好友A添加标签ID为3，同时保留已有的标签ID
        1和2。


        而在删除标签ID为1时，传递的参数如下：labelIds：2,3 ，wxIds：[wxid_asdfaihp123]。这表示要将好友A的标签ID
        1删除，而保留标签ID 2。
      tags:
        - 核心 API 模块/标签模块
        - 基础API/标签模块
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
                labelIds:
                  type: string
                  description: 标签ID，多个逗号分隔
                wxIds:
                  type: array
                  items:
                    type: string
                  description: 修改的好友wxid
              x-apifox-orders:
                - appId
                - labelIds
                - wxIds
              required:
                - appId
                - wxIds
                - labelIds
            example:
              appId: '{{appid}}'
              labelIds: '15'
              wxIds:
                - VideosApi
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
      x-apifox-folder: 核心 API 模块/标签模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454773-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
