# 扫码获取视频详情

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /finder/scanQrCode:
    post:
      summary: 扫码获取视频详情
      deprecated: false
      description: ''
      tags:
        - 核心 API 模块/视频号模块
        - 基础API/视频号模块
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
                myUserName:
                  type: string
                  description: 自己的username
                myRoleType:
                  type: integer
                  description: 自己的roletype
                qrContent:
                  type: string
                  description: 获取方式：官方视频号助手->内容管理->视频->复制视频链接
              required:
                - appId
                - myUserName
                - myRoleType
                - qrContent
              x-apifox-orders:
                - appId
                - myUserName
                - myRoleType
                - qrContent
            example:
              appId: '{{appid}}'
              useProxy: true
              myUserName: >-
                v2_060000231003b20faec8c7e28811c4d5cc0ded37b0779c48c759a7446a87688c2774e5300c32@finder
              myRoleType: 3
              qrContent: https://weixin.qq.com/sph/Apv77JRt5
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
                      object:
                        type: object
                        properties:
                          id:
                            type: integer
                            description: 作品ID
                          nickname:
                            type: string
                            description: 昵称
                          username:
                            type: string
                            description: 视频作者username
                          objectDesc:
                            type: object
                            properties:
                              description:
                                type: string
                                description: 作品描述
                              media:
                                type: array
                                items:
                                  type: object
                                  properties:
                                    Url:
                                      type: string
                                      description: 作品链接
                                    ThumbUrl:
                                      type: string
                                      description: 封面图链接
                                    MediaType:
                                      type: integer
                                    VideoPlayLen:
                                      type: integer
                                    Width:
                                      type: integer
                                      description: 视频高度
                                    Height:
                                      type: integer
                                      description: '视频宽度 '
                                    Md5Sum:
                                      type: string
                                      description: 文件MD5
                                    FileSize:
                                      type: integer
                                      description: 文件大小
                                    Bitrate:
                                      type: integer
                                    coverUrl:
                                      type: string
                                    decodeKey:
                                      type: string
                                    urlToken:
                                      type: string
                                    thumbUrlToken:
                                      type: string
                                    codecInfo:
                                      type: object
                                      properties:
                                        thumbScore:
                                          type: integer
                                        hdimgScore:
                                          type: integer
                                      required:
                                        - thumbScore
                                        - hdimgScore
                                      x-apifox-orders:
                                        - thumbScore
                                        - hdimgScore
                                    fullThumbUrl:
                                      type: string
                                    fullThumbUrlToken:
                                      type: string
                                    fullCoverUrl:
                                      type: string
                                    liveCoverImgs:
                                      type: array
                                      items:
                                        type: object
                                        properties:
                                          ThumbUrl:
                                            type: string
                                          FileSize:
                                            type: integer
                                          Width:
                                            type: integer
                                          Height:
                                            type: integer
                                          Bitrate:
                                            type: integer
                                        required:
                                          - ThumbUrl
                                          - FileSize
                                          - Width
                                          - Height
                                          - Bitrate
                                        x-apifox-orders:
                                          - ThumbUrl
                                          - FileSize
                                          - Width
                                          - Height
                                          - Bitrate
                                    cardShowStyle:
                                      type: integer
                                    dynamicRangeType:
                                      type: integer
                                    videoType:
                                      type: integer
                                  required:
                                    - Url
                                    - ThumbUrl
                                    - MediaType
                                    - VideoPlayLen
                                    - Width
                                    - Height
                                    - Md5Sum
                                    - FileSize
                                    - Bitrate
                                    - coverUrl
                                    - decodeKey
                                    - urlToken
                                    - thumbUrlToken
                                    - codecInfo
                                    - fullThumbUrl
                                    - fullThumbUrlToken
                                    - fullCoverUrl
                                    - liveCoverImgs
                                    - cardShowStyle
                                    - dynamicRangeType
                                    - videoType
                                  x-apifox-orders:
                                    - Url
                                    - ThumbUrl
                                    - MediaType
                                    - VideoPlayLen
                                    - Width
                                    - Height
                                    - Md5Sum
                                    - FileSize
                                    - Bitrate
                                    - coverUrl
                                    - decodeKey
                                    - urlToken
                                    - thumbUrlToken
                                    - codecInfo
                                    - fullThumbUrl
                                    - fullThumbUrlToken
                                    - fullCoverUrl
                                    - liveCoverImgs
                                    - cardShowStyle
                                    - dynamicRangeType
                                    - videoType
                              mediaType:
                                type: integer
                              location:
                                type: object
                                properties: {}
                                x-apifox-orders: []
                              extReading:
                                type: object
                                properties: {}
                                x-apifox-orders: []
                              topic:
                                type: object
                                properties:
                                  finderTopicInfo:
                                    type: string
                                required:
                                  - finderTopicInfo
                                x-apifox-orders:
                                  - finderTopicInfo
                              followPostInfo:
                                type: object
                                properties:
                                  musicInfo:
                                    type: object
                                    properties:
                                      docId:
                                        type: string
                                      albumThumbUrl:
                                        type: string
                                        description: 缩略图
                                      name:
                                        type: string
                                        description: 音乐名
                                      artist:
                                        type: string
                                        description: 作者名
                                      albumName:
                                        type: string
                                      mediaStreamingUrl:
                                        type: string
                                        description: 音乐播放链接
                                      miniappInfo:
                                        type: string
                                      webUrl:
                                        type: string
                                      floatThumbUrl:
                                        type: string
                                      chorusBegin:
                                        type: integer
                                      docType:
                                        type: integer
                                      songId:
                                        type: string
                                    required:
                                      - docId
                                      - albumThumbUrl
                                      - name
                                      - artist
                                      - albumName
                                      - mediaStreamingUrl
                                      - miniappInfo
                                      - webUrl
                                      - floatThumbUrl
                                      - chorusBegin
                                      - docType
                                      - songId
                                    x-apifox-orders:
                                      - docId
                                      - albumThumbUrl
                                      - name
                                      - artist
                                      - albumName
                                      - mediaStreamingUrl
                                      - miniappInfo
                                      - webUrl
                                      - floatThumbUrl
                                      - chorusBegin
                                      - docType
                                      - songId
                                    description: 背景音乐信息
                                  groupId:
                                    type: string
                                  hasBgm:
                                    type: integer
                                required:
                                  - musicInfo
                                  - groupId
                                  - hasBgm
                                x-apifox-orders:
                                  - musicInfo
                                  - groupId
                                  - hasBgm
                              fromApp:
                                type: object
                                properties: {}
                                x-apifox-orders: []
                              event:
                                type: object
                                properties: {}
                                x-apifox-orders: []
                              mvInfo:
                                type: object
                                properties: {}
                                x-apifox-orders: []
                              draftObjectId:
                                type: integer
                              clientDraftExtInfo:
                                type: object
                                properties:
                                  lbsFlagType:
                                    type: integer
                                  videoMusicId:
                                    type: string
                                required:
                                  - lbsFlagType
                                  - videoMusicId
                                x-apifox-orders:
                                  - lbsFlagType
                                  - videoMusicId
                              generalReportInfo:
                                type: object
                                properties: {}
                                x-apifox-orders: []
                              posterLocation:
                                type: object
                                properties:
                                  longitude:
                                    type: number
                                    description: 经度
                                  latitude:
                                    type: number
                                    description: 纬度
                                  city:
                                    type: string
                                    description: 城市
                                required:
                                  - longitude
                                  - latitude
                                  - city
                                x-apifox-orders:
                                  - longitude
                                  - latitude
                                  - city
                                description: 作品发布位置
                              shortTitle:
                                type: array
                                items:
                                  type: string
                              originalInfoDesc:
                                type: object
                                properties: {}
                                x-apifox-orders: []
                              finderNewlifeDesc:
                                type: object
                                properties: {}
                                x-apifox-orders: []
                            required:
                              - description
                              - media
                              - mediaType
                              - location
                              - extReading
                              - topic
                              - followPostInfo
                              - fromApp
                              - event
                              - mvInfo
                              - draftObjectId
                              - clientDraftExtInfo
                              - generalReportInfo
                              - posterLocation
                              - shortTitle
                              - originalInfoDesc
                              - finderNewlifeDesc
                            x-apifox-orders:
                              - description
                              - media
                              - mediaType
                              - location
                              - extReading
                              - topic
                              - followPostInfo
                              - fromApp
                              - event
                              - mvInfo
                              - draftObjectId
                              - clientDraftExtInfo
                              - generalReportInfo
                              - posterLocation
                              - shortTitle
                              - originalInfoDesc
                              - finderNewlifeDesc
                          createtime:
                            type: integer
                            description: 发布时间
                          likeFlag:
                            type: integer
                          likeList:
                            type: array
                            items:
                              type: string
                          forwardCount:
                            type: integer
                            description: 转发数
                          contact:
                            type: object
                            properties:
                              username:
                                type: string
                              nickname:
                                type: string
                              headUrl:
                                type: string
                              signature:
                                type: string
                              authInfo:
                                type: object
                                properties: {}
                                x-apifox-orders: []
                              coverImgUrl:
                                type: string
                              spamStatus:
                                type: integer
                              extFlag:
                                type: integer
                              extInfo:
                                type: object
                                properties:
                                  country:
                                    type: string
                                  province:
                                    type: string
                                  city:
                                    type: string
                                  sex:
                                    type: integer
                                required:
                                  - country
                                  - province
                                  - city
                                  - sex
                                x-apifox-orders:
                                  - country
                                  - province
                                  - city
                                  - sex
                              liveStatus:
                                type: integer
                              liveCoverImgUrl:
                                type: string
                              liveInfo:
                                type: object
                                properties:
                                  anchorStatusFlag:
                                    type: integer
                                  switchFlag:
                                    type: integer
                                  lotterySetting:
                                    type: object
                                    properties:
                                      settingFlag:
                                        type: integer
                                      attendType:
                                        type: integer
                                    required:
                                      - settingFlag
                                      - attendType
                                    x-apifox-orders:
                                      - settingFlag
                                      - attendType
                                required:
                                  - anchorStatusFlag
                                  - switchFlag
                                  - lotterySetting
                                x-apifox-orders:
                                  - anchorStatusFlag
                                  - switchFlag
                                  - lotterySetting
                              status:
                                type: integer
                            required:
                              - username
                              - nickname
                              - headUrl
                              - signature
                              - authInfo
                              - coverImgUrl
                              - spamStatus
                              - extFlag
                              - extInfo
                              - liveStatus
                              - liveCoverImgUrl
                              - liveInfo
                              - status
                            x-apifox-orders:
                              - username
                              - nickname
                              - headUrl
                              - signature
                              - authInfo
                              - coverImgUrl
                              - spamStatus
                              - extFlag
                              - extInfo
                              - liveStatus
                              - liveCoverImgUrl
                              - liveInfo
                              - status
                          likeCount:
                            type: integer
                            description: 点赞数
                          commentCount:
                            type: integer
                            description: 评论数
                          friendLikeCount:
                            type: integer
                            description: 好友点赞数
                          objectNonceId:
                            type: string
                            description: 作品Nonceid
                          objectStatus:
                            type: integer
                          sendShareFavWording:
                            type: string
                          originalFlag:
                            type: integer
                          secondaryShowFlag:
                            type: integer
                          favCount:
                            type: integer
                          favFlag:
                            type: integer
                          urlValidTime:
                            type: integer
                          forwardStyle:
                            type: integer
                          permissionFlag:
                            type: integer
                          objectType:
                            type: integer
                          followFeedCount:
                            type: integer
                          verifyInfoBuf:
                            type: string
                          wxStatusRefCount:
                            type: integer
                          adFlag:
                            type: integer
                          ringtoneCount:
                            type: integer
                          funcFlag:
                            type: integer
                          ipRegionInfo:
                            type: object
                            properties: {}
                            x-apifox-orders: []
                            description: 地区信息
                        required:
                          - id
                          - nickname
                          - username
                          - objectDesc
                          - createtime
                          - likeFlag
                          - likeList
                          - forwardCount
                          - contact
                          - likeCount
                          - commentCount
                          - friendLikeCount
                          - objectNonceId
                          - objectStatus
                          - sendShareFavWording
                          - originalFlag
                          - secondaryShowFlag
                          - favCount
                          - favFlag
                          - urlValidTime
                          - forwardStyle
                          - permissionFlag
                          - objectType
                          - followFeedCount
                          - verifyInfoBuf
                          - wxStatusRefCount
                          - adFlag
                          - ringtoneCount
                          - funcFlag
                          - ipRegionInfo
                        x-apifox-orders:
                          - id
                          - nickname
                          - username
                          - objectDesc
                          - createtime
                          - likeFlag
                          - likeList
                          - forwardCount
                          - contact
                          - likeCount
                          - commentCount
                          - friendLikeCount
                          - objectNonceId
                          - objectStatus
                          - sendShareFavWording
                          - originalFlag
                          - secondaryShowFlag
                          - favCount
                          - favFlag
                          - urlValidTime
                          - forwardStyle
                          - permissionFlag
                          - objectType
                          - followFeedCount
                          - verifyInfoBuf
                          - wxStatusRefCount
                          - adFlag
                          - ringtoneCount
                          - funcFlag
                          - ipRegionInfo
                      commentCount:
                        type: integer
                        description: 评论数
                      nextCheckObjectStatus:
                        type: integer
                    required:
                      - object
                      - commentCount
                      - nextCheckObjectStatus
                    x-apifox-orders:
                      - object
                      - commentCount
                      - nextCheckObjectStatus
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
                  object:
                    id: 14195037502970006000
                    nickname: 朝夕v
                    username: >-
                      v2_060000231003b20faec8c6e18f10c7d6c903ec3db0776955d3d97c6b329d6aa58693bcdb7ad1@finder
                    objectDesc:
                      description: ''
                      media:
                        - Url: >-
                            http://wxapp.tc.qq.com/251/20304/stodownload?encfilekey=oibeqyX228riaCwo9STVsGLPj9UYCicgttv57KAwaibwgt59R0ZvexpfcXpicuZgK9KrWFnqVIGCmmeEELsRrp14MS0oiaUOguD6XaicBEDD69qqNI2Qaa01Z17Yj56V9olerBgeGv5egDtHJ0&bizid=1023&dotrans=0&hy=SH&idx=1&m=82071545ea946d89af9ea5d6ad0fb576
                          ThumbUrl: >-
                            http://wxapp.tc.qq.com/251/20350/stodownload?encfilekey=oibeqyX228riaCwo9STVsGLPj9UYCicgttv1yP5Z57icAlHCbKIfJMyjc6w0oSrmEBrYXzewfFv2c6gkUHREmCrru0rTbTiaqV0Jvu83Sibd1JTfiaBTdCLQMjO8RQwlCjlC64lA3mHfKN3Jlc&bizid=1023&dotrans=0&hy=SH&idx=1&m=244c5c71db596838df691d372e7c0479&picformat=200
                          MediaType: 2
                          VideoPlayLen: 0
                          Width: 1440
                          Height: 1080
                          Md5Sum: ''
                          FileSize: 297437
                          Bitrate: 0
                          coverUrl: ''
                          decodeKey: '1249495775'
                          urlToken: >-
                            &token=Cvvj5Ix3eew5xyibexEnJ5wHgmp3icrpTu68qEau3f8kYibrgx0C7YJPXzPj5ZmZTrGDaVNPibNqDUluaAnQnYIgnGN0VlYn0RSIYoY8liaMNEe6lb4dvymCx1we4zvlw7Q3M&ctsc=154
                          thumbUrlToken: >-
                            &token=KkOFht0mCXkk40rrFZzjtRLINy4ASRjBT3GpxvY5LeFl3ibt0nm2JyM7A5SefhCxuIaCRLhh8H4aCoMHgTGpVuN23pbEZXtTm3dwjicXpRfmw&ctsc=1-154
                          codecInfo:
                            thumbScore: 12
                            hdimgScore: 45
                          fullThumbUrl: >-
                            http://wxapp.tc.qq.com/251/20350/stodownload?encfilekey=oibeqyX228riaCwo9STVsGLPj9UYCicgttv1yP5Z57icAlHCbKIfJMyjc6w0oSrmEBrYXzewfFv2c6gkUHREmCrru0rTbTiaqV0Jvu83Sibd1JTfiaBTdCLQMjO8RQwlCjlC64lA3mHfKN3Jlc&bizid=1023&dotrans=0&hy=SH&idx=1&m=244c5c71db596838df691d372e7c0479&picformat=200
                          fullThumbUrlToken: >-
                            &token=ic1n0xDG6awibsU5seGwWubKqKDaibhvFe7cNc4g5kibddUiafHicQmQSnP0AqPGO78ibPAstChRj8mVmy0DnNaibpLtmLTzfVCZdIUDyyyPbRwf6yA&ctsc=3-154
                          fullCoverUrl: ''
                          liveCoverImgs:
                            - ThumbUrl: >-
                                http://wxapp.tc.qq.com/251/20350/stodownload?encfilekey=oibeqyX228riaCwo9STVsGLPj9UYCicgttv1yP5Z57icAlHCbKIfJMyjc6w0oSrmEBrYXzewfFv2c6gkUHREmCrru0rTbTiaqV0Jvu83Sibd1JTfiaBTdCLQMjO8RQwlCjlC64lA3mHfKN3Jlc&bizid=1023&dotrans=0&hy=SH&idx=1&m=244c5c71db596838df691d372e7c0479
                              FileSize: 297437
                              Width: 1440
                              Height: 1080
                              Bitrate: 0
                          cardShowStyle: 0
                          dynamicRangeType: 0
                          videoType: 1
                        - Url: >-
                            http://wxapp.tc.qq.com/251/20304/stodownload?encfilekey=oibeqyX228riaCwo9STVsGLPj9UYCicgttvz7tHiay7nNxvJB3XKPvEuUhSdvoK3GckSDiaPJOqZnNaaTZibPYATvktg1qWDEShg5s6g8h79a1udSLNEdrRAPXwgQ4gG3HIyWOyA83V0WqYj0&bizid=1023&dotrans=0&hy=SH&idx=1&m=857ad08a06915c8fd77810d3a0bf6245
                          ThumbUrl: >-
                            http://wxapp.tc.qq.com/251/20350/stodownload?encfilekey=oibeqyX228riaCwo9STVsGLPj9UYCicgttvXia4icia4dYpVyxxmEmnFnndXTLqaibmOPXM2xQ5csekZIDZMOnTahH4bYYL8CsP1Fiadia7hb3y2ianicOjI4wsw8LicoSsOf8DUkGWJNoNc5pDE1FA&bizid=1023&dotrans=0&hy=SH&idx=1&m=e57a332f673663e810b4a7da0bf1e78e&picformat=200
                          MediaType: 2
                          VideoPlayLen: 0
                          Width: 1440
                          Height: 1080
                          Md5Sum: ''
                          FileSize: 326887
                          Bitrate: 0
                          coverUrl: ''
                          decodeKey: '2082100859'
                          urlToken: >-
                            &token=Cvvj5Ix3eew5xyibexEnJ5wHgmp3icrpTuRfgthRqkJo1ILSHgS8CrIYiajXoEsI3Od2cdGFcA5gtpgJFdGlnyXibGOTnA5Mjj57C286SKv1Nx82ibfRw5nWrXD5XDE9v12Wk&ctsc=154
                          thumbUrlToken: >-
                            &token=oA9SZ4icv8IsZenXlysnwuuxdic7Vq0GNRzqzddZpThibnDVkFeibXtr3BM3vIfI15IuYL4XZ4ed3PQZx1CRyJgT7n9gAd1OH2XlUZIRzxcV0ss&ctsc=1-154
                          codecInfo:
                            thumbScore: 12
                            hdimgScore: 45
                          fullThumbUrl: >-
                            http://wxapp.tc.qq.com/251/20350/stodownload?encfilekey=oibeqyX228riaCwo9STVsGLPj9UYCicgttvXia4icia4dYpVyxxmEmnFnndXTLqaibmOPXM2xQ5csekZIDZMOnTahH4bYYL8CsP1Fiadia7hb3y2ianicOjI4wsw8LicoSsOf8DUkGWJNoNc5pDE1FA&bizid=1023&dotrans=0&hy=SH&idx=1&m=e57a332f673663e810b4a7da0bf1e78e&picformat=200
                          fullThumbUrlToken: >-
                            &token=KkOFht0mCXknX5dyibFbricEsibuX5GcA3AOSmtpQrB2rgYdU0FOnE9kTqeDt2PKrc459w86XlluKT2N3byELLzJ7WdyIHibaFHGiaUImGnNamIc&ctsc=3-154
                          fullCoverUrl: ''
                          liveCoverImgs:
                            - ThumbUrl: >-
                                http://wxapp.tc.qq.com/251/20350/stodownload?encfilekey=oibeqyX228riaCwo9STVsGLPj9UYCicgttvXia4icia4dYpVyxxmEmnFnndXTLqaibmOPXM2xQ5csekZIDZMOnTahH4bYYL8CsP1Fiadia7hb3y2ianicOjI4wsw8LicoSsOf8DUkGWJNoNc5pDE1FA&bizid=1023&dotrans=0&hy=SH&idx=1&m=e57a332f673663e810b4a7da0bf1e78e
                              FileSize: 326887
                              Width: 1440
                              Height: 1080
                              Bitrate: 0
                          cardShowStyle: 0
                          dynamicRangeType: 0
                          videoType: 1
                      mediaType: 2
                      location: {}
                      extReading: {}
                      topic:
                        finderTopicInfo: ''
                      followPostInfo:
                        musicInfo:
                          docId: '342066328'
                          albumThumbUrl: >-
                            http://wx.y.gtimg.cn/music/photo_new/T002R500x500M000001kWuR62LAvku_1.jpg
                          name: monsters
                          artist: 苏天伦
                          albumName: ''
                          mediaStreamingUrl: >-
                            https://cover.qpic.cn/206/20302/stodownload?m=b8c992316fbfde34eadf7c76051035ee&filekey=30350201010421301f020200ce040253480410b8c992316fbfde34eadf7c76051035ee02030f703a040d00000004627466730000000131&hy=SH&storeid=323032323039323330353036323130303035363831663139613364666266356336386234306230303030303063653030303034663465&bizid=1023
                          miniappInfo: ''
                          webUrl: ''
                          floatThumbUrl: ''
                          chorusBegin: 0
                          docType: 0
                          songId: ''
                        groupId: '342066328'
                        hasBgm: 1
                      fromApp: {}
                      event: {}
                      mvInfo: {}
                      draftObjectId: 14195067577171968000
                      clientDraftExtInfo:
                        lbsFlagType: 0
                        videoMusicId: '342066328'
                      generalReportInfo: {}
                      posterLocation:
                        longitude: 116.642105
                        latitude: 34.687767
                        city: Xuzhou City
                      shortTitle:
                        - CgA=
                      originalInfoDesc: {}
                      finderNewlifeDesc: {}
                    createtime: 1692180335
                    likeFlag: 0
                    likeList:
                      - >-
                        Cg56aGFuZ2NodWFuMjI4OBIJ5pyd5aSV44CCGgAgvpKAj+jsuf/EASgAOq0BaHR0cHM6Ly93eC5xbG9nby5jbi9tbWhlYWQvdmVyXzEvcEJSaWNkQjNIOTRFcFQ4UFFKM05Ya2xpYzU5WDdYU3NncENKMFRWMXZjcHVxUWxpYjdNSkdHc2JuWk80djBDRjQ4aWNRb0lKUDljbURBcVR4cWJ6MmlidGlhazh6cEl4RTcwMDV3Nmlhb1hiaWJWVEN3UkdFVXV4U2R3bGMwdGNETjZRSVdVSC8xMzJI0JmzrAZgAKoBAA==
                    forwardCount: 1
                    contact:
                      username: >-
                        v2_060000231003b20faec8c6e18f10c7d6c903ec3db0776955d3d97c6b329d6aa58693bcdb7ad1@finder
                      nickname: 朝夕v
                      headUrl: >-
                        https://wx.qlogo.cn/finderhead/ver_1/TDibw5X5xTzpMW9D4GE0YnYUMqPAspF0AibTwhdSFWjyt2tZCMuLVon1PIT6aGulvzvlSZPkDcT06NB6D1eoLicYBKiaBCRDXZJSMEErIGQkQJ8/0
                      signature: 。。。
                      authInfo: {}
                      coverImgUrl: ''
                      spamStatus: 0
                      extFlag: 262156
                      extInfo:
                        country: CN
                        province: Jiangsu
                        city: Xuzhou
                        sex: 2
                      liveStatus: 2
                      liveCoverImgUrl: >-
                        http://wxapp.tc.qq.com/251/20350/stodownload?m=be88b1cb981aa72b3328ccbd22a58e0b&filekey=30340201010420301e020200fb040253480410be88b1cb981aa72b3328ccbd22a58e0b02022814040d00000004627466730000000132&hy=SH&storeid=5649443df0009b8a38399cc84000000fb00004f7e534815c008e0b08dc805c&dotrans=0&bizid=1023
                      liveInfo:
                        anchorStatusFlag: 133248
                        switchFlag: 53727
                        lotterySetting:
                          settingFlag: 0
                          attendType: 4
                      status: 0
                    likeCount: 2
                    commentCount: 5
                    friendLikeCount: 1
                    objectNonceId: '16628169456191691547_0_154_0_0'
                    objectStatus: 0
                    sendShareFavWording: ''
                    originalFlag: 0
                    secondaryShowFlag: 1
                    favCount: 3
                    favFlag: 1
                    urlValidTime: 172800
                    forwardStyle: 0
                    permissionFlag: 2147483648
                    objectType: 0
                    followFeedCount: 17
                    verifyInfoBuf: >-
                      CrADD3QLRKZljCPO5dJ958TJct7WbHzU3lM4r1PJtQpm8vbngWNGW346SKEAwM8tRL25uHNJfTR0co1F4k76AQY1EDg2GyDaz4PGCeyfiSP5uN6xS0sdYGw+ln0TdVVk1/clsefJAGJscIYDcfTms18Dkw4D79zgBGq3luGMY1TGRcjkopsxRvvYKYwB995y3pZXK9DisP1v1jA5ecMrXKuJDI5qIe6O5SYUk+OY5WQtTRZwELDojU/SiuuZ9eZFf2IkWUGL5FHHBxHB7WX3JcoNPyi0zLHyCVdBBkPIebN/w2RwCbwSXLGO+tqg3XYIRD3PC7ALOU1Hum+jwtUczQIqkFTaQZ+q99DdpMv1yYi5D2zCWxni0r/IfjqvuFSoumfErCW5DMDgny4kRZ4lqRhw0d4EDCLEz4Daz3q+vTIAme8yoWk4O8Wvb8FKvZIjjtSYCkXJLl9feh5oPaFsp8mzLrYCcAze+Lwac+0+e0bJRCtLAiw4BAn+CoyBqhfoJHo6QgGsf4j3CEyY9xxZtQDFyLPEW7vCIJF9tM7a5raqZdHCV13OkgvxKa7hhUNELD3P
                    wxStatusRefCount: 0
                    adFlag: 4
                    ringtoneCount: 0
                    funcFlag: 288
                    ipRegionInfo: {}
                  commentCount: 5
                  nextCheckObjectStatus: 30
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/视频号模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454806-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
