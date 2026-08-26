# 转发朋友圈

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /sns/forwardSns:
    post:
      summary: 转发朋友圈
      deprecated: false
      description: >
        在新设备登录后的1-3天内，您将无法使用朋友圈发布、点赞、评论等功能。在此期间，如果尝试进行这些操作，您将收到来自微信团队的提醒。请注意遵守相关规定。
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
                allowWxIds:
                  type: array
                  items:
                    type: string
                    description: 好友的wxid
                  description: 允许谁看
                atWxIds:
                  type: array
                  items:
                    type: string
                    description: 好友的wxid
                  description: 提醒谁看
                disableWxIds:
                  type: array
                  items:
                    type: string
                    description: 好友的wxid
                  description: 不给谁看
                privacy:
                  type: boolean
                  description: 是否私密
                  default: 'false'
                  nullable: true
                snsXml:
                  type: string
                  description: 朋友圈xml
              x-apifox-orders:
                - appId
                - allowWxIds
                - atWxIds
                - disableWxIds
                - privacy
                - snsXml
              required:
                - appId
                - allowWxIds
                - atWxIds
                - disableWxIds
                - snsXml
            example:
              appId: '{{appid}}'
              allowWxIds: []
              atWxIds: []
              disableWxIds: []
              snsXml: >-
                <TimelineObject><id><![CDATA[14287710809635828232]]></id><username><![CDATA[wxid_g66c3f6y1eg922]]></username><createTime><![CDATA[1703227855]]></createTime><contentDescShowType>0</contentDescShowType><contentDescScene>0</contentDescScene><private><![CDATA[0]]></private><contentDesc></contentDesc><contentattr><![CDATA[0]]></contentattr><sourceUserName><![CDATA[]]></sourceUserName><sourceNickName><![CDATA[狮子领域
                程序圈]]></sourceNickName><statisticsData></statisticsData><weappInfo><appUserName></appUserName><pagePath></pagePath><version><![CDATA[0]]></version><isHidden>0</isHidden><debugMode><![CDATA[0]]></debugMode><shareActionId></shareActionId><isGame><![CDATA[0]]></isGame><messageExtraData></messageExtraData><subType><![CDATA[0]]></subType><preloadResources></preloadResources></weappInfo><canvasInfoXml></canvasInfoXml><ContentObject><contentStyle><![CDATA[3]]></contentStyle><contentSubStyle><![CDATA[0]]></contentSubStyle><title><![CDATA[RuoYi-Vue-Plus
                发布 5.1.2 版本 2023 最后一版]]></title><description><![CDATA[
                ]]></description><contentUrl><![CDATA[http://mp.weixin.qq.com/s?__biz=Mzg4MDYyMzQ5OQ==&mid=2247488653&idx=1&sn=4adf3b791d46d25a117368acea19bd30&chksm=cf733e69f804b77f1fc08a994c41fb76ea933200b7cd484fa8b4fee8b810b1dd78a340c4cb83&mpshare=1&scene=2&srcid=1222KNQu96XLoOwcMuphqc5q&sharer_shareinfo=9689a1855d235961b3bc8f49f788da34&sharer_shareinfo_first=9689a1855d235961b3bc8f49f788da34#rd]]></contentUrl><mediaList><media><id><![CDATA[14287710810308162053]]></id><type><![CDATA[2]]></type><title></title><description></description><private><![CDATA[0]]></private><url
                type="1"><![CDATA[http://shmmsns.qpic.cn/mmsns/C5Hh7IZThT42LQAraZkUG3bIHHicRLQeuzibCs1FqoIw0KSaQus3BleoNwvSSRcKnd200SBRM0cks/0]]></url><thumb
                type="1"><![CDATA[http://shmmsns.qpic.cn/mmsns/C5Hh7IZThT42LQAraZkUG3bIHHicRLQeuzibCs1FqoIw0KSaQus3BleoNwvSSRcKnd200SBRM0cks/150]]></thumb><videoDuration><![CDATA[0.0]]></videoDuration><size
                totalSize="3636.0" width="150.0"
                height="150.0"></size></media></mediaList><mmreadershare><itemshowtype>0</itemshowtype><ispaysubscribe>0</ispaysubscribe></mmreadershare></ContentObject><actionInfo><appMsg><mediaTagName></mediaTagName><messageExt></messageExt><messageAction></messageAction></appMsg></actionInfo><statExtStr></statExtStr><appInfo><id></id></appInfo><location
                poiClassifyId="" poiName="" poiAddress="" poiClassifyType="0"
                city=""></location><publicUserName>gh_23471f7470c1</publicUserName><streamvideo><streamvideourl></streamvideourl><streamvideothumburl></streamvideothumburl><streamvideoweburl></streamvideoweburl></streamvideo></TimelineObject>
              privacy: false
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
                      id:
                        type: integer
                        description: 朋友圈ID
                      userName:
                        type: string
                        description: 朋友圈作者的wxid
                      nickName:
                        type: string
                        description: 朋友圈作者的昵称
                      createTime:
                        type: integer
                        description: 发布时间
                    required:
                      - id
                      - userName
                      - nickName
                      - createTime
                    x-apifox-orders:
                      - id
                      - userName
                      - nickName
                      - createTime
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
                  id: 14292805435261587000
                  userName: VideosApi
                  nickName: 苏生
                  createTime: 1703835181
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/朋友圈模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454765-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
