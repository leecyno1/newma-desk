# 下载朋友圈视频

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /sns/downloadSnsVideo:
    post:
      summary: 下载朋友圈视频
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
                snsXml:
                  type: string
                  description: 获取到的朋友圈xml
              x-apifox-orders:
                - appId
                - snsXml
              required:
                - appId
                - snsXml
            example:
              appId: '{{appid}}'
              snsXml: snsXml
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
                      fileUrl:
                        type: string
                    x-apifox-orders:
                      - fileUrl
                required:
                  - ret
                  - msg
                x-apifox-orders:
                  - ret
                  - msg
                  - data
              example:
                ret: 200
                msg: 操作成功
                data:
                  fileUrl: >-
                    http://oos-sccd.ctyunapi.cn/20240403/wx_sP8zmJIXLkWupGnKoF/04847c12-cf2a-4850-9b8e-2d3b40190aaa.mp4?AWSAccessKeyId=9e882e7187c38b431303&Expires=1712720598&Signature=i2%2FwckXedEf%2BYvg1Az%2FHJ2VWL9E%3D
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/朋友圈模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454758-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
