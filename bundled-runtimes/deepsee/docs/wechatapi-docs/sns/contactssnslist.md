# 联系人的朋友圈列表

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /sns/contactsSnsList:
    post:
      summary: 联系人的朋友圈列表
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
                maxId:
                  type: number
                  description: 首次传0，第二页及以后传接口返回的maxId
                decrypt:
                  type: boolean
                  description: 是否解密
                  default: 'true'
                wxid:
                  type: string
                  description: 好友wxid
                firstPageMd5:
                  type: string
                  description: 首次传空，第二页及以后传接口返回的firstPageMd5
              x-apifox-orders:
                - appId
                - maxId
                - decrypt
                - wxid
                - firstPageMd5
              required:
                - appId
                - wxid
            example:
              appId: '{{appid}}'
              maxId: 0
              decrypt: true
              wxid: VideosApi
              firstPageMd5: ''
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
                    additionalProperties: false
                  msg:
                    type: string
                    additionalProperties: false
                  data:
                    type: object
                    properties:
                      firstPageMd5:
                        type: string
                        description: 翻页key
                        additionalProperties: false
                      maxId:
                        type: integer
                        description: 列表最后一条的snsId
                        additionalProperties: false
                      snsCount:
                        type: integer
                        description: 条数
                        additionalProperties: false
                      requestTime:
                        type: integer
                        description: 请求时间
                        additionalProperties: false
                      snsList:
                        type: array
                        items:
                          type: object
                          properties:
                            id:
                              type: integer
                              description: 朋友圈ID
                              additionalProperties: false
                            userName:
                              type: string
                              description: 朋友圈作者的wxid
                              additionalProperties: false
                            nickName:
                              type: string
                              description: 朋友圈作者的昵称
                              additionalProperties: false
                            createTime:
                              type: integer
                              description: 发布时间
                              additionalProperties: false
                            snsXml:
                              type: string
                              description: 朋友圈的xml，可用于转发朋友圈
                              additionalProperties: false
                            likeCount:
                              type: integer
                              description: 点赞数
                              additionalProperties: false
                            likeList:
                              type: 'null'
                              description: 点赞好友的信息
                              additionalProperties: false
                            commentCount:
                              type: integer
                              description: 评论数
                              additionalProperties: false
                            commentList:
                              type: 'null'
                              description: 评论的内容
                              additionalProperties: false
                            withUserCount:
                              type: integer
                              description: 提醒谁看的数量
                              additionalProperties: false
                            withUserList:
                              type: 'null'
                              description: 提醒谁看的wxid
                              additionalProperties: false
                          required:
                            - id
                            - userName
                            - nickName
                            - createTime
                            - snsXml
                            - likeCount
                            - likeList
                            - commentCount
                            - commentList
                            - withUserCount
                            - withUserList
                          x-apifox-orders:
                            - id
                            - userName
                            - nickName
                            - createTime
                            - snsXml
                            - likeCount
                            - likeList
                            - commentCount
                            - commentList
                            - withUserCount
                            - withUserList
                    required:
                      - firstPageMd5
                      - maxId
                      - snsCount
                      - requestTime
                      - snsList
                    x-apifox-orders:
                      - firstPageMd5
                      - maxId
                      - snsCount
                      - requestTime
                      - snsList
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
                  firstPageMd5: 5b6cd464e80df435
                  maxId: 14020472144428995000
                  snsCount: 10
                  requestTime: 1703833537
                  snsList:
                    - id: 14214000407987818000
                      userName: VideosApi
                      nickName: 苏生
                      createTime: 1694440890
                      snsXml: >-
                        <TimelineObject><id>14214000407987819068</id><username>zhangchuan2288</username><createTime>1694440890</createTime><contentDesc>搁置了一个月的战车，出门蹬一会被撞了，忘了躺地上，错失一个换车的机会。[苦涩][苦涩]</contentDesc><contentDescShowType>0</contentDescShowType><contentDescScene>3</contentDescScene><private>0</private><sightFolded>0</sightFolded><showFlag>0</showFlag><appInfo><id></id><version></version><appName></appName><installUrl></installUrl><fromUrl></fromUrl><isForceUpdate>0</isForceUpdate><isHidden>0</isHidden></appInfo><sourceUserName></sourceUserName><sourceNickName></sourceNickName><statisticsData></statisticsData><statExtStr></statExtStr><ContentObject><contentStyle>1</contentStyle><title></title><description></description><mediFzeKA69P5uIdqPfQxp59LpevPpX0bJz1zbXSpiavc01kia9H4cic0dJbHbUEJDibB8jx2oXfnBuKhgg/0</url><thuma></mediaList><contentUrl></contentUrl></ContentObject><actionInfo><appMsg><messageAction></messageAction></appMsg></actionInfo><location
                        poiClassifyId="" poiName="" poiAddress=""
                        poiClassifyType="0"
                        city=""></location><publicUserName></publicUserName><streamvideo><streamvideourl></streamvideourl><streamvideothumburl></streamvideothumburl><streamvideoweburl></streamvideoweburl></streamvideo></TimelineObject>
                      likeCount: 4
                      likeList:
                        - userName: '*******'
                          nickName: 糖果
                          source: 0
                          type: 1
                          createTime: 1694440920
                        - userName: '********'
                          nickName: 挽风～
                          source: 0
                          type: 1
                          createTime: 1694441103
                        - userName: '********'
                          nickName: ^^辻弌^^
                          source: 0
                          type: 1
                          createTime: 1694441218
                        - userName: '********'
                          nickName: 丶zoū zoú zoǔ zoù 👾
                          source: 0
                          type: 1
                          createTime: 1694455325
                      commentCount: 19
                      commentList:
                        - userName: '********'
                          nickName: ME
                          source: 0
                          type: 2
                          content: 去医院验伤 索赔
                          createTime: 1694441070
                          commentId: 1
                          replyCommentId: 0
                          isNotRichText: 1
                        - userName: '********'
                          nickName: 故事的小黄花
                          source: 0
                          type: 2
                          content: 懂车帝没下载好？
                          createTime: 1694441111
                          commentId: 33
                          replyCommentId: 0
                          isNotRichText: 1
                        - userName: '********'
                          nickName: 朝夕。
                          source: 0
                          type: 2
                          content: 来不及了，赔了点钱就让走了[捂脸]
                          createTime: 1694441270
                          commentId: 65
                          replyCommentId: 1
                          isNotRichText: 1
                        - userName: '********'
                          nickName: 挽风～
                          source: 0
                          type: 2
                          content: 对方在想:那人竟然没躺地上，感觉他像自己赚了一个亿那么开心[破涕为笑]
                          createTime: 1694441274
                          commentId: 97
                          replyCommentId: 0
                          isNotRichText: 1
                        - userName: '********'
                          nickName: ME
                          source: 0
                          type: 2
                          content: 报警 你说验出严重的伤了
                          createTime: 1694441302
                          commentId: 129
                          replyCommentId: 65
                          isNotRichText: 1
                        - userName: '********'
                          nickName: 朝夕。
                          source: 0
                          type: 2
                          content: 没来得及，错失良机
                          createTime: 1694441314
                          commentId: 161
                          replyCommentId: 33
                          isNotRichText: 1
                        - userName: '********'
                          nickName: 朝夕。
                          source: 0
                          type: 2
                          content: 我都看出来他的开心了😃
                          createTime: 1694441371
                          commentId: 193
                          replyCommentId: 97
                          isNotRichText: 1
                        - userName: '********'
                          nickName: 朝夕。
                          source: 0
                          type: 2
                          content: 就是影响心情，倒是也没啥
                          createTime: 1694441407
                          commentId: 225
                          replyCommentId: 129
                          isNotRichText: 1
                        - userName: '********'
                          nickName: 灼
                          source: 0
                          type: 2
                          content: 车胎昨天刚爆[捂脸]
                          createTime: 1694441828
                          commentId: 259
                          replyCommentId: 0
                          isNotRichText: 1
                        - userName: '********'
                          nickName: 朝夕。
                          source: 0
                          type: 2
                          content: 正好歇着
                          createTime: 1694442074
                          commentId: 289
                          replyCommentId: 259
                          isNotRichText: 1
                        - userName: '********'
                          nickName: 宋端雅
                          source: 0
                          type: 2
                          content: 去医院，你有保险，咱不怕
                          createTime: 1694442081
                          commentId: 321
                          replyCommentId: 0
                          isNotRichText: 1
                        - userName: '********'
                          nickName: 朝夕。
                          source: 0
                          type: 2
                          content: 忘了这茬。有没有自行车险，我买一个[破涕为笑][破涕为笑]
                          createTime: 1694442193
                          commentId: 353
                          replyCommentId: 321
                          isNotRichText: 1
                        - userName: '********'
                          nickName: 宋端雅
                          source: 0
                          type: 2
                          content: 价值太低了，不值当的[捂脸]
                          createTime: 1694442243
                          commentId: 385
                          replyCommentId: 353
                          isNotRichText: 1
                        - userName: '********'
                          nickName: 灼
                          source: 0
                          type: 2
                          content: 一个月爆了两次[苦涩]，都没法看小姑娘了
                          createTime: 1694442381
                          commentId: 419
                          replyCommentId: 289
                          isNotRichText: 1
                        - userName: '********'
                          nickName: 朝夕。
                          source: 0
                          type: 2
                          content: 哪有小姑娘，我骑共享单车也得去
                          createTime: 1694442448
                          commentId: 449
                          replyCommentId: 419
                          isNotRichText: 1
                        - userName: '********'
                          nickName: 灼
                          source: 0
                          type: 2
                          content: 金龙湖，大龙湖，你来
                          createTime: 1694442524
                          commentId: 483
                          replyCommentId: 449
                          isNotRichText: 1
                        - userName: '********'
                          nickName: 文强
                          source: 0
                          type: 2
                          content: 我看你胖了，是把车轱辘压拍圈了吧
                          createTime: 1694488063
                          commentId: 513
                          replyCommentId: 0
                          isNotRichText: 1
                        - userName: '********'
                          nickName: 朝夕。
                          source: 0
                          type: 2
                          content: 哎日，几年不见了，你不能来请我吃个饭吗
                          createTime: 1694488128
                          commentId: 545
                          replyCommentId: 513
                          isNotRichText: 1
                        - userName: '********'
                          nickName: 文强
                          source: 0
                          type: 2
                          content: 你个哪了
                          createTime: 1694488297
                          commentId: 577
                          replyCommentId: 545
                          isNotRichText: 1
                      withUserCount: 0
                      withUserList: null
                    - id: 14208277753875796000
                      userName: '********'
                      nickName: 朝夕。
                      createTime: 1693758696
                      snsXml: >-
                        <TimelineObject><id>14208277753875796533</id><username>zhangchuan2288</username><createTime>1693758696</createTime><contentDesc>家门口的tr><ContentObject><contentStyle>1</contentStyle><title></title><description></description><mediaList><media><id>14208277754493801017</id><type>2</type><title></title><description>家门口的音乐节总要支持一下[旺柴]</description><private>0</private><userData></userData><subType>0</subType><videoSize
                        width="4032" height="3024"></videoSize><url type="1"
                        md5="4d92355ce00a69a285fbaacc1fb87235"
                        videomd5="">http://shmmsns.qpic.cn/mmsns/FzeKA69P5uIdqPfQxp59LpoVDy1G6vico1v9waHyDEl9jAnE0BM4VTe36JnQX47MaNfiad3qFErmA/0</url><thumb
                        type="1">http://<media><id>14208277754512347715</id><type>2</type><title></title><description></description><private>0</private><userData></userData><subType>0</subType><videoSize
                        width="4032" height="3024"></videoSize><url type="1"
                        md5="93805b62afce77664432bd42da707197"
                        videomd5="">http://shmmsns.qpic.cn/mmsns/FzeKA69P5uIdqPfQxp59LpoVDy1G6vicoMsvmIUmgPSHJvfuTvX8zlezQZiaf8tmuvb4oajtczSUU/0</url><thumb
                        type="1">http://shmmsns.qpic.cn/mmsns/FzeKA69P5uIdqPfQxp59LpoVDy1G6vicoMsvmIUmgPSHJvfuTvX8zlezQZiaf8tmuvb4oajtczSUU/150</thumb><size
                        width="1440.000000" height="1080.000000"
                        totalSize="109173"></size><"
                        videomd5="">http://shmmsns.qpic.cn/mmsns/FzeKA69P5uIdqPfQxp59LpoVDy1G6vicoib5UxwljGHSAaYGyUUum0ia0XpiamvtbYnwNiaJbex9COKc/0</url><thumb
                        type="1">http://shmmsns.qpic.cn/mmsns/FzeKA69P5uIdqPfQxp59LpoVDy1G6vicoib5UxwljGHSAaYGyUUum0ia0XpiamvtbYnwNiaJbex9COKc/150</thumb><size
                        width="1440.000000" height="1080.000000"
                        totalSize="25581"></size></media><media><id>14208277754538037822</id><type>2</type><title></title><description></description><private>0</private><userData></userData><subType>0</subType><videoSize
                        width="2954" height="3675"></videoSize><url type="1"
                        md5="620712b48f108661d376da70e86080dc"
                        videomd5="">http://shmmsns.qpic.cn/mmsns/FzeKA69P5uIdqPfQxp59LpoVDy1G6vicoVia0ibt106s3VZlj2uwYgaPWDUjy9BpvbuZ8G3Fptojlw/0</url><thumb
                        type="1">http://shion></description><private>0</private><userData></userData><subType>0</subType><videoSize
                        width="844" height="532"></videoSize><url type="1"
                        md5="2763fbc86db233e000893f7800d22ae0"
                        videomd5="">http://shmmsns.qpic.cn/mmsns/FzeKA69P5uIdqPfQxp59LpoVDy1G6vico75qcUzI3g9OQ2tyDicmramD6iaRibPjd2MeicaHVWjZa0nI/0</url><thumb
                        type="1">http://shmmsns.qpic.cn/mmsns/FzeKA69P5uIdqPfQxp59LpoVDy1G6vico75qcUzI3g9OQ2tyDicmramD6iaRibPjd2MeicaHVWjZa0nI/150</thumb><size
                        width="844.000000" height="532.000000"
                        totalSize="16133"></size></media><media><id>14208277754564645437</id><type>2</type><title></title><description></description><private>0</private><userData></userData><subType>0</subType><videoSize
                        width="4032" height="3024"></videoSize><url type="1"
                        md5="e4bb6e50fe77634482fb08e22948c88d"
                        videomd5="">http://shmmsns.qpic.cn/mmsns/FzeKA69P5uIdqPfQxp59LpoVDy1G6vicoAkMpJrc0SdNfZ1DRQjXWqQf8yIEs50cdDic2uxXP01F8/0</url><thumb
                        type="1">http://shmmsnName="" poiAddress=""
                        poiClassifyType="0"
                        city=""></location><publicUserName></publicUserName><streamvideo><streamvideourl></streamvideourl><streamvideothumburl></streamvideothumburl><streamvideoweburl></streamvideoweburl></streamvideo></TimelineObject>
                      likeCount: 18
                      likeList:
                        - userName: '********'
                          nickName: 朝夕。
                          source: 0
                          type: 1
                          createTime: 1693758719
                        - userName: '********'
                          nickName: 糖果
                          source: 0
                          type: 1
                          createTime: 1693758752
                        - userName: '********'
                          nickName: 暖心
                          source: 0
                          type: 1
                          createTime: 1693758848
                        - userName: '********'
                          nickName: 沧海候鸟
                          source: 0
                          type: 1
                          createTime: 1693759534
                        - userName: '********'
                          nickName: Mr李
                          source: 0
                          type: 1
                          createTime: 1693762812
                        - userName: '********'
                          nickName: Sunny girl🌼
                          source: 0
                          type: 1
                          createTime: 1693764342
                        - userName: '********'
                          nickName: Ch.
                          source: 0
                          type: 1
                          createTime: 1693764442
                        - userName: '********'
                          nickName: 小小晴仔🐳
                          source: 0
                          type: 1
                          createTime: 1693774829
                        - userName: '********'
                          nickName: A刘腾A
                          source: 0
                          type: 1
                          createTime: 1693778449
                        - userName: '********'
                          nickName: 王路
                          source: 0
                          type: 1
                          createTime: 1693780908
                        - userName: '********'
                          nickName: 永不放弃
                          source: 0
                          type: 1
                          createTime: 1693781785
                        - userName: '********'
                          nickName: 🐑咩咩🐭咪吖🐒
                          source: 0
                          type: 1
                          createTime: 1693786930
                        - userName: '********'
                          nickName: 群青
                          source: 0
                          type: 1
                          createTime: 1693787156
                        - userName: '********'
                          nickName: ^^辻弌^^
                          source: 0
                          type: 1
                          createTime: 1693787189
                        - userName: '********'
                          nickName: 奔跑的子弹
                          source: 0
                          type: 1
                          createTime: 1693787766
                        - userName: '********'
                          nickName: JUST DO IT
                          source: 0
                          type: 1
                          createTime: 1693788096
                        - userName: '********'
                          nickName: 江苏水蓝.张传飞
                          source: 0
                          type: 1
                          createTime: 1693791225
                        - userName: '********'
                          nickName: _C_
                          source: 0
                          type: 1
                          createTime: 1693808488
                      commentCount: 8
                      commentList:
                        - userName: '********'
                          nickName: 凪卄
                          source: 0
                          type: 2
                          content: 咋脸那么大
                          createTime: 1693758905
                          commentId: 1
                          replyCommentId: 0
                          isNotRichText: 1
                        - userName: '********'
                          nickName: 朝夕。
                          source: 0
                          type: 2
                          content: 是的，朴树也该减肥了
                          createTime: 1693758974
                          commentId: 33
                          replyCommentId: 1
                          isNotRichText: 1
                        - userName: '********'
                          nickName: 那些你很冒险的梦
                          source: 0
                          type: 2
                          content: '********'
                          createTime: 1693759044
                          commentId: 65
                          replyCommentId: 0
                          isNotRichText: 1
                        - userName: '********'
                          nickName: 朝夕。
                          source: 0
                          type: 2
                          content: 距离十几公里[破涕为笑]
                          createTime: 1693759125
                          commentId: 97
                          replyCommentId: 65
                          isNotRichText: 1
                        - userName: '********'
                          nickName: 永不放弃
                          source: 0
                          type: 2
                          content: '********'
                          createTime: 1693782120
                          commentId: 131
                          replyCommentId: 0
                          isNotRichText: 1
                        - userName: '********'
                          nickName: 朝夕。
                          source: 0
                          type: 2
                          content: '[笑脸][笑脸]'
                          createTime: 1693791930
                          commentId: 161
                          replyCommentId: 131
                          isNotRichText: 1
                        - userName: '********'
                          nickName: _C_
                          source: 0
                          type: 2
                          content: 周末不加班你跑去喂蚊子[旺柴]
                          createTime: 1693808512
                          commentId: 195
                          replyCommentId: 0
                          isNotRichText: 1
                        - userName: '********'
                          nickName: 朝夕。
                          source: 0
                          type: 2
                          content: 音乐节上敲代码你是没看到
                          createTime: 1693811409
                          commentId: 225
                          replyCommentId: 195
                          isNotRichText: 1
                      withUserCount: 0
                      withUserList: null
                    - id: 14020472144428995000
                      userName: '********'
                      nickName: 朝夕。
                      createTime: 1671370523
                      snsXml: >-
                        <TimelineObject><id>14020472144428994892</id><username>zhangchuan2288</username><createTime>1671370523</createTime><contentDesc>各位亲/fromUrl><isForceUpdate>0</isForceUpdate></appInfo><sourceUserName></sourceUserName><sourceNickName></sourceNickName><statisticsData></statisticsData><statExtStr></statExtStr><ContentObject><contentStyle>2</contentStyle><title></title><description></description><mediaList></mediaList><contentUrl></contentUrl></ContentObject><actionInfo><appMsg><messageAction></messageAction></appMsg></actionInfo><location
                        poiClassifyId="" poiName="" poiAddress=""
                        poiClassifyType="0"
                        city=""></location><publicUserName></publicUserName><streamvideo><streamvideourl></streamvideourl><streamvideothumburl></streamvideothumburl><streamvideoweburl></streamvideoweburl></streamvideo></TimelineObject>
                      likeCount: 10
                      likeList:
                        - userName: zhangchuan2288
                          nickName: 朝夕。
                          source: 0
                          type: 1
                          createTime: 1671371441
                        - userName: '********'
                          nickName: 呵呵
                          source: 0
                          type: 1
                          createTime: 1671371892
                        - userName: '********'
                          nickName: 远方
                          source: 0
                          type: 1
                          createTime: 1671372088
                        - userName: '********'
                          nickName: 小小晴仔🐳
                          source: 0
                          type: 1
                          createTime: 1671373801
                        - userName: '********'
                          nickName: X-zzzz
                          source: 0
                          type: 1
                          createTime: 1671374936
                        - userName: '********'
                          nickName: 曼妍美甲美睫美容养生会所
                          source: 0
                          type: 1
                          createTime: 1671375069
                        - userName: '********'
                          nickName: 落婲丶無痕
                          source: 0
                          type: 1
                          createTime: 1671377256
                        - userName: '********'
                          nickName: 王富贵
                          source: 0
                          type: 1
                          createTime: 1671379054
                        - userName: '********'
                          nickName: 大乞丐
                          source: 0
                          type: 1
                          createTime: 1671408286
                        - userName: '********'
                          nickName: 咩咩咪丫
                          source: 0
                          type: 1
                          createTime: 1671408463
                      commentCount: 2
                      commentList:
                        - userName: '********'
                          nickName: 大鸭梨
                          source: 0
                          type: 2
                          content: 这书面通知写的很有文采[旺柴][旺柴]
                          createTime: 1671380865
                          commentId: 1
                          replyCommentId: 0
                          isNotRichText: 1
                        - userName: '********'
                          nickName: 朝夕。
                          source: 0
                          type: 2
                          content: 毕竟只改了个日期[破涕为笑]
                          createTime: 1671412735
                          commentId: 33
                          replyCommentId: 1
                          isNotRichText: 1
                      withUserCount: 0
                      withUserList: null
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/朋友圈模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454767-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
