# 上传朋友圈视频

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /sns/uploadSnsVideo:
    post:
      summary: 上传朋友圈视频
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
                  nullable: true
                thumbUrl:
                  type: string
                  description: 视频封面图片链接
                  nullable: true
                videoUrl:
                  type: string
                  description: 视频文件链接
                  nullable: true
              x-apifox-orders:
                - appId
                - thumbUrl
                - videoUrl
              required:
                - appId
                - thumbUrl
                - videoUrl
            example:
              appId: '{{appid}}'
              thumbUrl: http://dummyimage.com/400x400
              videoUrl: >-
                https://scrm-1308498490.cos.ap-shanghai.myqcloud.com/pkg/436fa030-18a45a6e917.mp4?q-sign-algorithm=sha1&q-ak=AKIDmOkqfDUUDfqjMincBSSAbleGaeQv96mB&q-sign-time=1703834932;1703842132&q-key-time=1703834932;1703842132&q-header-list=&q-url-param-list=&q-signature=985cb175fc372408498498294f5c8ddf13a13cfb
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
                        description: 上传视频的文件链接
                      thumbUrl:
                        type: string
                        description: 上传视频的缩略图链接
                      fileMd5:
                        type: string
                        description: 视频的md5
                      length:
                        type: integer
                        description: 视频文件的大小
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
              example:
                ret: 200
                msg: 操作成功
                data:
                  fileUrl: >-
                    http://szzjwxsns.video.qq.com/102/20202/snsvideodownload?filekey=30340201010420301e0201660402535a04106e95f9d79588843ac259b780f0cbf20f020314148b040d00000004627466730000000132&hy=SZ&storeid=5658e7541000080a98399cc840000006600004eea535a236b0181565ff0c9a&dotrans=9&ef=30_0&ut=6xykWLEnztInqJIccsNnmJnFIIMYTDicqsNxakAGmcmW1hOicyiayN6Cw&ui=1&bizid=1023&ilogo=2&dur=7&upid=500030
                  thumbUrl: >-
                    http://vweixinthumb.tc.qq.com/150/20250/snsvideodownload?filekey=30340201010420301e020200960402535a0410704de7ebbc107a51a4f0986253a6d3b602020448040d00000004627466730000000132&hy=SZ&storeid=5658e7541000065838399cc840000009600004f1a535a236cc15156605b59d&bizid=1023
                  fileMd5: 6e95f9d79588843ac259b780f0cbf20f
                  length: 1315979
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/朋友圈模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454764-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
