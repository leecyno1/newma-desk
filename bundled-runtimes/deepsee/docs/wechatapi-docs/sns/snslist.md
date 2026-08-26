# 自己的朋友圈列表

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /sns/snsList:
    post:
      summary: 自己的朋友圈列表
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
                firstPageMd5:
                  type: string
                  description: 首次传空，第二页及以后传接口返回的firstPageMd5
              x-apifox-orders:
                - appId
                - maxId
                - decrypt
                - firstPageMd5
              required:
                - appId
            example:
              appId: '{{appid}}'
              maxId: 0
              decrypt: true
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
                  msg:
                    type: string
                  data:
                    type: object
                    properties:
                      firstPageMd5:
                        type: string
                        description: 翻页key
                      maxId:
                        type: integer
                        description: 列表最后一条的snsId
                      snsCount:
                        type: integer
                        description: 条数
                      requestTime:
                        type: integer
                        description: 请求时间
                      snsList:
                        type: array
                        items:
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
                            snsXml:
                              type: string
                              description: 朋友圈的xml，可用于转发朋友圈
                            likeCount:
                              type: integer
                              description: 点赞数
                            likeList:
                              type: 'null'
                              description: 点赞好友的wxid
                            commentCount:
                              type: integer
                              description: 评论数
                            commentList:
                              type: 'null'
                              description: 评论的内容
                            withUserCount:
                              type: integer
                              description: 提醒谁看的数量
                            withUserList:
                              type: 'null'
                              description: 提醒谁看的wxid
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
                  firstPageMd5: 2eb48afd4862ddc8
                  maxId: 14287734111135740000
                  snsCount: 10
                  requestTime: 1703236186
                  snsList:
                    - id: 14287779828924756000
                      userName: wxid_***********
                      nickName: 王娇
                      createTime: 1703236082
                      snsXml: >-
                        <TimelineObject><id><![CDATA[14287779828924756671]]></id><username><![CDATA[wxid_thd7lxtbjblp22]]></username><createTime><![CDATA[1703236082]]></createTime><contentDescShowType>0</contentDescShowType><contentDescScene>0</contentDescScene><private><![CDATA[0]]></private><contentDesc><![CDATA[年化3.55
                        公积金满1000就可以办理]]></contentDesc><contentattr><![CDATA[0]]></contentattr><sourceUserName></sourceUserName><sourceNickName></sourceNickName><statisticsData></statisticsData><weappInfo><appUserName></appUserName><pagePath></pagePath><version><![CDATA[0]]></version><debugMode><![CDATA[0]]></debugMode><shareActionId></shareActionId><isGame><![CDATA[0]]></isGame><messageExtraData></messageExtraData><subType><![CDATA[0]]></subType><preloadResources></preloadResources></weappInfo><canvasInfoXml></canvasInfoXml><ContentObject><contentStyle><![CDATA[1]]></contentStyle><contentSubStyle><![CDATA[0]]></contentSubStyle><title></title><description></description><contentUrl></contentUrl><mediaList><media><id><![CDATA[14287779829602333383]]></id><type><![CDATA[2]]></type><title></title><description></description><private><![CDATA[0]]></private><url
                        type="1"
                        md5="d001e2d7e551242dc9187e71773f28cb"><![CDATA[http://shmmsns.qpic.cn/mmsns/7cM5CRSLxfDHTVo1aBzEYdpNmn8pX0dtn6ibhauZBqCibV0tm5Pf2tq6cSTnRY4icM5nN1LcCicsPiaI/0]]></url><thumb
                        type="1"><![CDATA[http://shmmsns.qpic.cn/mmsns/7cM5CRSLxfDHTVo1aBzEYdpNmn8pX0dtn6ibhauZBqCibV0tm5Pf2tq6cSTnRY4icM5nN1LcCicsPiaI/150]]></thumb><videoDuration><![CDATA[0.0]]></videoDuration><size
                        totalSize="63166.0" width="1080.0"
                        height="1440.0"></size></media></mediaList></ContentObject><actionInfo><appMsg><mediaTagName></mediaTagName><messageExt></messageExt><messageAction></messageAction></appMsg></actionInfo><appInfo><id></id></appInfo><location
                        poiClassifyId="" poiName="" poiAddress=""
                        poiClassifyType="0"
                        city=""></location><publicUserName></publicUserName><streamvideo><streamvideourl></streamvideourl><streamvideothumburl></streamvideothumburl><streamvideoweburl></streamvideoweburl></streamvideo></TimelineObject>
                      likeCount: 0
                      likeList: null
                      commentCount: 0
                      commentList: null
                      withUserCount: 0
                      withUserList: null
                    - id: 14287777324036526000
                      userName: wxid_***********
                      nickName: 任寅
                      createTime: 1703235784
                      snsXml: >-
                        <TimelineObject><id>14287777324036526701</id><username>wxid_***********</username><createTime>1703235784</createTime><contentDesc>[庆祝]新卡易贷，冰点‮回价‬馈&#x0A;[太阳]年化利率3.18%起（单利计算）&#x0A;[鼓掌]信‮额用‬度高达50万(我行房贷‮最客‬高100W)&#x0A;[礼物]可先息后本，额‮循度‬环&#x0A;[拳头]上门团办，高‮审效‬批</contentDesc><contentDescShowType>1</contentDescShowType><contentDescScene>3</contentDescScene><private>0</private><sightFolded>0</sightFolded><showFlag>0</showFlag><appInfo><id></id><version></version><appName></appName><installUrl></installUrl><fromUrl></fromUrl><isForceUpdate>0</isForceUpdate><isHidden>0</isHidden></appInfo><sourceUserName></sourceUserName><sourceNickName></sourceNickName><statisticsData></statisticsData><statExtStr></statExtStr><ContentObject><contentStyle>1</contentStyle><title></title><description></description><mediaList><media><id>14287777324490887803</id><type>2</type><title></title><description>[庆祝]新卡易贷，冰点‮回价‬馈&#x0A;[太阳]年化利率3.18%起（单利计算）&#x0A;[鼓掌]信‮额用‬度高达50万(我行房贷‮最客‬高100W)&#x0A;[礼物]可先息后本，额‮循度‬环&#x0A;[拳头]上门团办，高‮审效‬批</description><private>0</private><userData></userData><subType>0</subType><videoSize
                        width="1080" height="1947"></videoSize><url type="1"
                        md5="b790996e0ec1e961430c0e0bd1b87919"
                        videomd5="">http://shmmsns.qpic.cn/mmsns/7MykMgNAr8Ckyc5tGOdUBDDoJYI54mTHdkibYTOf5j3baZnewCPcV6Pia2wQxDkVGJb0W6Z4lH474/0</url><thumb
                        type="1">http://shmmsns.qpic.cn/mmsns/7MykMgNAr8Ckyc5tGOdUBDDoJYI54mTHdkibYTOf5j3baZnewCPcV6Pia2wQxDkVGJb0W6Z4lH474/150</thumb><size
                        width="1080.000000" height="1947.000000"
                        totalSize="77664"></size></media></mediaList><contentUrl></contentUrl></ContentObject><actionInfo><appMsg><messageAction></messageAction></appMsg></actionInfo><location
                        poiClassifyId="" poiName="" poiAddress=""
                        poiClassifyType="0"
                        city=""></location><publicUserName></publicUserName><streamvideo><streamvideourl></streamvideourl><streamvideothumburl></streamvideothumburl><streamvideoweburl></streamvideoweburl></streamvideo></TimelineObject>
                      likeCount: 0
                      likeList: null
                      commentCount: 0
                      commentList: null
                      withUserCount: 0
                      withUserList: null
                    - id: 14287770802419536000
                      userName: wxid_***********
                      nickName: 花笙里花艺气球
                      createTime: 1703235006
                      snsXml: >-
                        <TimelineObject><id>14287770802419536384</id><username>wxid_***********</username><createTime>1703235006</createTime><contentDesc>客订圣诞树🎄</contentDesc><contentDescShowType>0</contentDescShowType><contentDescScene>0</contentDescScene><private>0</private><sightFolded>0</sightFolded><showFlag>0</showFlag><appInfo><id></id><version></version><appName></appName><installUrl></installUrl><fromUrl></fromUrl><isForceUpdate>0</isForceUpdate><isHidden>0</isHidden></appInfo><sourceUserName></sourceUserName><sourceNickName></sourceNickName><statisticsData></statisticsData><statExtStr></statExtStr><ContentObject><contentStyle>15</contentStyle><title>微信小视频</title><description>Sight</description><mediaList><media><id>14287770803199939062</id><type>6</type><title></title><description>客订圣诞树🎄</description><private>0</private><userData></userData><subType>0</subType><videoSize
                        width="720" height="1280"></videoSize><url type="1"
                        md5="65363e2409c934368115b3a5e25923ac"
                        videomd5="2c41a7e273e4aa9ee51a6ea7215b2609">http://shzjwxsns.video.qq.com/102/20202/snsvideodownload?filekey=30340201010420301e02016604025348041065363e2409c934368115b3a5e25923ac0203290a93040d00000004627466730000000132&amp;hy=SH&amp;storeid=565854dbd000e7ec0283837a70000006600004eea53480aa39031573aa361f&amp;dotrans=9&amp;ef=30_0&amp;bizid=1023&amp;ilogo=2&amp;dur=12&amp;upid=290110</url><thumb
                        type="1">http://vweixinthumb.tc.qq.com/150/20250/snsvideodownload?filekey=30340201010420301e02020096040253480410c310e3e2f7820dd5c9c76e76643b26dd020265d9040d00000004627466730000000132&amp;hy=SH&amp;storeid=565854dbd000d6a68283837a70000009600004f1a53482aa8cbc1e67344c31&amp;bizid=1023</thumb><size
                        width="224.000000" height="398.000000"
                        totalSize="2689683"></size><videoDuration>12.309000</videoDuration><VideoColdDLRule><All>CAISBAgWEAEoAjAc</All></VideoColdDLRule></media></mediaList><contentUrl>https://support.weixin.qq.com/cgi-bin/mmsupport-bin/readtemplate?t=page/common_page__upgrade&amp;v=1</contentUrl></ContentObject><actionInfo><appMsg><messageAction></messageAction></appMsg></actionInfo><location
                        poiClassifyId="" poiName="" poiAddress=""
                        poiClassifyType="0"
                        city=""></location><publicUserName></publicUserName><streamvideo><streamvideourl></streamvideourl><streamvideothumburl></streamvideothumburl><streamvideoweburl></streamvideoweburl></streamvideo></TimelineObject>
                      likeCount: 0
                      likeList: null
                      commentCount: 0
                      commentList: null
                      withUserCount: 0
                      withUserList: null
                    - id: 14287761219266286000
                      userName: wxid_pjhkdf7uywtd12
                      nickName: A 绿洲洗衣连锁13701469587
                      createTime: 1703233864
                      snsXml: >-
                        <TimelineObject><id>14287761219266286277</id><username>wxid_pjhkdf7uywtd12</username><createTime>1703233864</createTime><contentDesc>今天冬至，本店已下班，小伙伴们别跑空哦！</contentDesc><contentDescShowType>0</contentDescShowType><contentDescScene>3</contentDescScene><private>0</private><sightFolded>0</sightFolded><showFlag>0</showFlag><appInfo><id></id><version></version><appName></appName><installUrl></installUrl><fromUrl></fromUrl><isForceUpdate>0</isForceUpdate><isHidden>0</isHidden></appInfo><sourceUserName></sourceUserName><sourceNickName></sourceNickName><statisticsData></statisticsData><statExtStr></statExtStr><ContentObject><contentStyle>1</contentStyle><title></title><description></description><mediaList><media><id>14287761219887108802</id><type>2</type><title></title><description>今天冬至，本店已下班，小伙伴们别跑空哦！</description><private>0</private><userData></userData><subType>0</subType><videoSize
                        width="1920" height="1080"></videoSize><url type="1"
                        md5="f97e824d9af8f913bad6531b76c6f295"
                        videomd5="">http://shmmsns.qpic.cn/mmsns/PnFhfibQibZXPjibeNjjW2wLlficFiatLibNK6hDn1nicwYAIhpjUSia43yruTPRBicKwSeicJJ8OjpWloKXw/0</url><thumb
                        type="1">http://shmmsns.qpic.cn/mmsns/PnFhfibQibZXPjibeNjjW2wLlficFiatLibNK6hDn1nicwYAIhpjUSia43yruTPRBicKwSeicJJ8OjpWloKXw/150</thumb><size
                        width="1920.000000" height="1080.000000"
                        totalSize="174343"></size></media></mediaList><contentUrl></contentUrl></ContentObject><actionInfo><appMsg><messageAction></messageAction></appMsg></actionInfo><location
                        poiClassifyId="" poiName="" poiAddress=""
                        poiClassifyType="0"
                        city=""></location><publicUserName></publicUserName><streamvideo><streamvideourl></streamvideourl><streamvideothumburl></streamvideothumburl><streamvideoweburl></streamvideoweburl></streamvideo></TimelineObject>
                      likeCount: 0
                      likeList: null
                      commentCount: 0
                      commentList: null
                      withUserCount: 0
                      withUserList: null
                    - id: 14287760836481192000
                      userName: wxid_pjhkdf7uywtd12
                      nickName: A 绿洲洗衣连锁13701469587
                      createTime: 1703233818
                      snsXml: >-
                        <TimelineObject><id>14287760836481192643</id><username>wxid_pjhkdf7uywtd12</username><createTime>1703233818</createTime><contentDesc>今天4点下班，带来不便，敬请谅解！小伙伴们需要取衣服的别跑空哦！</contentDesc><contentDescShowType>0</contentDescShowType><contentDescScene>3</contentDescScene><private>0</private><sightFolded>0</sightFolded><showFlag>0</showFlag><appInfo><id></id><version></version><appName></appName><installUrl></installUrl><fromUrl></fromUrl><isForceUpdate>0</isForceUpdate><isHidden>0</isHidden></appInfo><sourceUserName></sourceUserName><sourceNickName></sourceNickName><statisticsData></statisticsData><statExtStr></statExtStr><ContentObject><contentStyle>1</contentStyle><title></title><description></description><mediaList><media><id>14287760836919038655</id><type>2</type><title></title><description>今天4点下班，带来不便，敬请谅解！小伙伴们需要取衣服的别跑空哦！</description><private>0</private><userData></userData><subType>0</subType><videoSize
                        width="1920" height="1080"></videoSize><url type="1"
                        md5="f97e824d9af8f913bad6531b76c6f295"
                        videomd5="">http://shmmsns.qpic.cn/mmsns/PnFhfibQibZXPjibeNjjW2wLodQqRg6ejEUQkwhro4CjG7NSdZMicENLrPb299Ky5HzJftV7R90MHT4/0</url><thumb
                        type="1">http://shmmsns.qpic.cn/mmsns/PnFhfibQibZXPjibeNjjW2wLodQqRg6ejEUQkwhro4CjG7NSdZMicENLrPb299Ky5HzJftV7R90MHT4/150</thumb><size
                        width="1920.000000" height="1080.000000"
                        totalSize="174343"></size></media></mediaList><contentUrl></contentUrl></ContentObject><actionInfo><appMsg><messageAction></messageAction></appMsg></actionInfo><location
                        poiClassifyId="" poiName="" poiAddress=""
                        poiClassifyType="0"
                        city=""></location><publicUserName></publicUserName><streamvideo><streamvideourl></streamvideourl><streamvideothumburl></streamvideothumburl><streamvideoweburl></streamvideoweburl></streamvideo></TimelineObject>
                      likeCount: 0
                      likeList: null
                      commentCount: 0
                      commentList: null
                      withUserCount: 0
                      withUserList: null
                    - id: 14287755418877300000
                      userName: wxid_4mb3zx0q09fq21
                      nickName: 花笙里花艺气球  武警17772257273
                      createTime: 1703233172
                      snsXml: >-
                        <TimelineObject><id>14287755418877301240</id><username>wxid_4mb3zx0q09fq21</username><createTime>1703233172</createTime><contentDesc>礼盒款来了</contentDesc><contentDescShowType>0</contentDescShowType><contentDescScene>0</contentDescScene><private>0</private><sightFolded>0</sightFolded><showFlag>0</showFlag><appInfo><id></id><version></version><appName></appName><installUrl></installUrl><fromUrl></fromUrl><isForceUpdate>0</isForceUpdate><isHidden>0</isHidden></appInfo><sourceUserName></sourceUserName><sourceNickName></sourceNickName><statisticsData></statisticsData><statExtStr></statExtStr><ContentObject><contentStyle>15</contentStyle><title>微信小视频</title><description>Sight</description><mediaList><media><id>14287755419476693503</id><type>6</type><title></title><description>礼盒款来了</description><private>0</private><userData></userData><subType>0</subType><videoSize
                        width="720" height="1280"></videoSize><url type="1"
                        md5="159a2c16de0f907ec0e9a2b620ba5588"
                        videomd5="2246b66261a58b2b2bf97345878af647">http://shzjwxsns.video.qq.com/102/20202/snsvideodownload?filekey=30340201010420301e020166040253480410159a2c16de0f907ec0e9a2b620ba558802030d2714040d00000004627466730000000132&amp;hy=SH&amp;storeid=56585469400039031283837a70000006600004eea53482fe35b00b747cb60b&amp;dotrans=1&amp;ef=30_0&amp;bizid=1023&amp;ilogo=2&amp;dur=14&amp;upid=500220</url><thumb
                        type="1">http://vweixinthumb.tc.qq.com/150/20250/snsvideodownload?filekey=30340201010420301e0202009604025348041059e68e82b666ea8762263d875c7643c3020274c0040d00000004627466730000000132&amp;hy=SH&amp;storeid=56585469400031c0e283837a70000009600004f1a53480fe3d03156924853d&amp;bizid=1023</thumb><size
                        width="224.000000" height="398.000000"
                        totalSize="861972"></size><videoDuration>14.329000</videoDuration><VideoColdDLRule><All>CAISBAgWEAEoAjAc</All></VideoColdDLRule></media></mediaList><contentUrl>https://support.weixin.qq.com/cgi-bin/mmsupport-bin/readtemplate?t=page/common_page__upgrade&amp;v=1</contentUrl></ContentObject><actionInfo><appMsg><messageAction></messageAction></appMsg></actionInfo><location
                        poiClassifyId="" poiName="" poiAddress=""
                        poiClassifyType="0"
                        city=""></location><publicUserName></publicUserName><streamvideo><streamvideourl></streamvideourl><streamvideothumburl></streamvideothumburl><streamvideoweburl></streamvideoweburl></streamvideo></TimelineObject>
                      likeCount: 0
                      likeList: null
                      commentCount: 0
                      commentList: null
                      withUserCount: 0
                      withUserList: null
                    - id: 14287752581719069000
                      userName: wxid_***********
                      nickName: 可可～
                      createTime: 1703232834
                      snsXml: >-
                        <TimelineObject><id>14287752581719069335</id><username>wxid_***********</username><createTime>1703232834</createTime><contentDesc>夏天变冬天</contentDesc><contentDescShowType>0</contentDescShowType><contentDescScene>0</contentDescScene><private>0</private><sightFolded>0</sightFolded><showFlag>0</showFlag><appInfo><id></id><version></version><appName></appName><installUrl></installUrl><fromUrl></fromUrl><isForceUpdate>0</isForceUpdate><isHidden>0</isHidden></appInfo><sourceUserName></sourceUserName><sourceNickName></sourceNickName><statisticsData></statisticsData><statExtStr></statExtStr><ContentObject><contentStyle>15</contentStyle><title>微信小视频</title><description>Sight</description><mediaList><media><id>14287752582549803671</id><type>6</type><title></title><description>夏天变冬天</description><private>0</private><userData></userData><subType>0</subType><videoSize
                        width="720" height="1280"></videoSize><url type="1"
                        md5="a06c73286db3ef0c0c726ad08a625b73"
                        videomd5="72c44f1d9c66a3a60a2b81409f9c7fa6">http://shzjwxsns.video.qq.com/102/20202/snsvideodownload?filekey=30340201010420301e020166040253480410a06c73286db3ef0c0c726ad08a625b73020337e141040d00000004627466730000000132&amp;hy=SH&amp;storeid=565854541000c6e177b359fcd0000006600004eea534802506bd1e7c5f28ea&amp;dotrans=10&amp;ef=30_0&amp;bizid=1023&amp;dur=3&amp;upid=500250</url><thumb
                        type="1">http://vweixinthumb.tc.qq.com/150/20250/snsvideodownload?filekey=30340201010420301e02020096040253480410b83b4ff949c0f0a1c7511632773a096b02027065040d00000004627466730000000132&amp;hy=SH&amp;storeid=565854541000b0f467b359fcd0000009600004f1a53480258abc1e6fc10b7a&amp;bizid=1023</thumb><size
                        width="224.000000" height="398.000000"
                        totalSize="3662145"></size><videoDuration>3.584000</videoDuration><VideoColdDLRule><All>CAISBAgWEAEoAjAc</All></VideoColdDLRule></media></mediaList><contentUrl>https://support.weixin.qq.com/cgi-bin/mmsupport-bin/readtemplate?t=page/common_page__upgrade&amp;v=1</contentUrl></ContentObject><VideoTemplate><Type>miaojian</Type><TemplateId>mv_creator_23611db0b7b54748b6e5ba97efa970ba</TemplateId><MusicId>4:1530091529305194496:1</MusicId><VersionInfo><IosSdkVersionMin>1004000</IosSdkVersionMin><AndroidSdkVersionMin>1004000</AndroidSdkVersionMin></VersionInfo></VideoTemplate><actionInfo><appMsg><messageAction></messageAction></appMsg></actionInfo><location
                        poiClassifyId="" poiName="" poiAddress=""
                        poiClassifyType="0"
                        city=""></location><publicUserName></publicUserName><streamvideo><streamvideourl></streamvideourl><streamvideothumburl></streamvideothumburl><streamvideoweburl></streamvideoweburl></streamvideo></TimelineObject>
                      likeCount: 0
                      likeList: null
                      commentCount: 0
                      commentList: null
                      withUserCount: 0
                      withUserList: null
                    - id: 14287736959729742000
                      userName: wxid_ypzeeovk3r0d22
                      nickName: 马士兵教育~洁如（14:00-23:00）
                      createTime: 1703230972
                      snsXml: >-
                        <TimelineObject><id><![CDATA[14287736959729742329]]></id><username><![CDATA[wxid_ypzeeovk3r0d22]]></username><createTime><![CDATA[1703230972]]></createTime><contentDescShowType>0</contentDescShowType><contentDescScene>0</contentDescScene><private><![CDATA[0]]></private><contentDesc><![CDATA[还在纠结的同学，抓紧上了[呲牙][呲牙][呲牙]]]></contentDesc><contentattr><![CDATA[0]]></contentattr><sourceUserName></sourceUserName><sourceNickName></sourceNickName><statisticsData></statisticsData><weappInfo><appUserName></appUserName><pagePath></pagePath><version><![CDATA[0]]></version><isHidden>0</isHidden><debugMode><![CDATA[0]]></debugMode><shareActionId></shareActionId><isGame><![CDATA[0]]></isGame><messageExtraData></messageExtraData><subType><![CDATA[0]]></subType><preloadResources></preloadResources></weappInfo><canvasInfoXml></canvasInfoXml><ContentObject><contentStyle><![CDATA[1]]></contentStyle><contentSubStyle><![CDATA[0]]></contentSubStyle><title></title><description></description><contentUrl></contentUrl><mediaList><media><id><![CDATA[14287736960327627271]]></id><type><![CDATA[2]]></type><title></title><description></description><private><![CDATA[0]]></private><url
                        type="1"
                        md5="349614433ba258bd41d25626c098c6cd"><![CDATA[http://shmmsns.qpic.cn/mmsns/4owBl1bibWAeYSXAZSHmJ9bHVwUg8nhvAuicR2o0ZR50OYs97cIVI6lJic3O9C9kQv7SBN3miaVwsAw/0]]></url><thumb
                        type="1"><![CDATA[http://shmmsns.qpic.cn/mmsns/4owBl1bibWAeYSXAZSHmJ9bHVwUg8nhvAuicR2o0ZR50OYs97cIVI6lJic3O9C9kQv7SBN3miaVwsAw/150]]></thumb><videoDuration><![CDATA[0.0]]></videoDuration><size
                        totalSize="26716.0" width="753.0"
                        height="557.0"></size></media></mediaList></ContentObject><actionInfo><appMsg><mediaTagName></mediaTagName><messageExt></messageExt><messageAction></messageAction></appMsg></actionInfo><appInfo><id></id></appInfo><location
                        poiClassifyId="" poiName="" poiAddress=""
                        poiClassifyType="0"
                        city=""></location><publicUserName></publicUserName><streamvideo><streamvideourl></streamvideourl><streamvideothumburl></streamvideothumburl><streamvideoweburl></streamvideoweburl></streamvideo></TimelineObject>
                      likeCount: 0
                      likeList: null
                      commentCount: 0
                      commentList: null
                      withUserCount: 0
                      withUserList: null
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/朋友圈模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454766-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
