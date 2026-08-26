# 上传朋友圈图片

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /sns/uploadSnsImage:
    post:
      summary: 上传朋友圈图片
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
                imgUrls:
                  type: array
                  items:
                    type: string
                    description: 图片链接
                    minLength: 1
                    maxLength: 9
                  description: 图片链接
              x-apifox-orders:
                - appId
                - imgUrls
              required:
                - appId
                - imgUrls
            example:
              appId: '{{appid}}'
              imgUrls:
                - http://dummyimage.com/400x400
                - http://dummyimage.com/400x300
                - http://dummyimage.com/400x400
                - http://dummyimage.com/400x300
                - http://dummyimage.com/400x400
                - http://dummyimage.com/400x300
                - http://dummyimage.com/400x400
                - http://dummyimage.com/400x300
                - http://dummyimage.com/400x300
                - http://dummyimage.com/400x300
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
                    type: array
                    items:
                      type: object
                      properties:
                        fileUrl:
                          type: string
                          description: 上传图片的链接
                        thumbUrl:
                          type: string
                          description: 上传图片的缩略图链接
                        fileMd5:
                          type: string
                          description: 图片的md5
                        length:
                          type: integer
                          description: 图片的文件大小
                      required:
                        - fileUrl
                        - thumbUrl
                        - fileMd5
                        - length
                      x-apifox-orders:
                        - fileUrl
                        - thumbUrl
                        - fileMd5
                        - length
                required:
                  - ret
                  - msg
                  - data
                x-apifox-orders:
                  - ret
                  - msg
                  - data
              examples:
                '1':
                  summary: 成功示例
                  value:
                    ret: 200
                    msg: 操作成功
                    data:
                      - fileUrl: >-
                          http://szmmsns.qpic.cn/mmsns/FzeKA69P5uJr4JZ7M7h6bAeMo2q3AKbyA2aqtKtBTibicSJdhlBuc30AMOCFkCYdnCxleUX35NBBE/0
                        thumbUrl: >-
                          http://szmmsns.qpic.cn/mmsns/FzeKA69P5uJr4JZ7M7h6bAeMo2q3AKbyA2aqtKtBTibicSJdhlBuc30AMOCFkCYdnCxleUX35NBBE/150
                        fileMd5: 704de7ebbc107a51a4f0986253a6d3b6
                        length: 1096
                      - fileUrl: >-
                          http://szmmsns.qpic.cn/mmsns/FzeKA69P5uJr4JZ7M7h6bAeMo2q3AKby5mg2I3C20yLn95mWHQ0dC4hqWosWyf1zf43Xmut3CCE/0
                        thumbUrl: >-
                          http://szmmsns.qpic.cn/mmsns/FzeKA69P5uJr4JZ7M7h6bAeMo2q3AKby5mg2I3C20yLn95mWHQ0dC4hqWosWyf1zf43Xmut3CCE/150
                        fileMd5: f34ccc016a83c23d11b94f9c4ef533f3
                        length: 1086
                '2':
                  summary: 异常示例
                  value:
                    ret: 500
                    msg: imgUrls不可为空
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/朋友圈模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454763-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
