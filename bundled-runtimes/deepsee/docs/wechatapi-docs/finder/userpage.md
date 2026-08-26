# 获取用户主页(所有视频)

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /finder/userPage:
    post:
      summary: 获取用户主页(所有视频)
      deprecated: false
      description: |
        :::highlight green 
        1.本接口使用对方toUserName为v2开头
        2.获取本人视频时,privateFlag字段为视频是否隐藏,公开的视频不会返回此字段
        :::
        注：V2可在消息回调接口内取到（fromusername）
        如果对方私信身份为视频号身份则返回V2开头、则可以获取。若私信身份为微信身份则返回为FV1开头，无法进行获取。。
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
                toUserName:
                  type: string
                  description: 用户的username
                lastBuffer:
                  type: string
                  description: 首次传空，后续传接口返回的lastBuffer
                maxId:
                  type: integer
                  description: 首次传0，后续传响应结果中最后一条的id
                searchInfo:
                  type: object
                  properties:
                    cookies:
                      type: string
                    searchId:
                      type: string
                  x-apifox-orders:
                    - cookies
                    - searchId
                  description: 如果是通过搜索渠道获取用户主页，则把搜索接口返回的cookies、searchId传进来
              required:
                - appId
                - toUserName
              x-apifox-orders:
                - appId
                - toUserName
                - lastBuffer
                - maxId
                - searchInfo
            example:
              appId: '{{appid}}'
              lastBuffer: ''
              toUserName: >-
                v2_060000231003b20faec8cae7811bcadcc904ef30b0770fd600f70cfec5c128fc2ef6421e0c7a@finder
              maxId: 0
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
                        type: array
                        items:
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
                              description: username
                            objectDesc:
                              type: object
                              properties:
                                description:
                                  type: string
                                media:
                                  type: array
                                  items:
                                    type: object
                                    properties:
                                      Url:
                                        type: string
                                      ThumbUrl:
                                        type: string
                                      MediaType:
                                        type: integer
                                      VideoPlayLen:
                                        type: integer
                                      Width:
                                        type: integer
                                      Height:
                                        type: integer
                                      Md5Sum:
                                        type: string
                                      FileSize:
                                        type: integer
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
                                imgFeedBgmInfo:
                                  type: object
                                  properties:
                                    docId:
                                      type: string
                                    albumThumbUrl:
                                      type: string
                                    name:
                                      type: string
                                    artist:
                                      type: string
                                    albumName:
                                      type: string
                                    mediaStreamingUrl:
                                      type: string
                                  required:
                                    - docId
                                    - albumThumbUrl
                                    - name
                                    - artist
                                    - albumName
                                    - mediaStreamingUrl
                                  x-apifox-orders:
                                    - docId
                                    - albumThumbUrl
                                    - name
                                    - artist
                                    - albumName
                                    - mediaStreamingUrl
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
                                        name:
                                          type: string
                                        artist:
                                          type: string
                                        albumName:
                                          type: string
                                        mediaStreamingUrl:
                                          type: string
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
                                    latitude:
                                      type: number
                                    city:
                                      type: string
                                  required:
                                    - longitude
                                    - latitude
                                    - city
                                  x-apifox-orders:
                                    - longitude
                                    - latitude
                                    - city
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
                                - imgFeedBgmInfo
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
                                - imgFeedBgmInfo
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
                              description: 创建时间
                            likeList:
                              type: array
                              items:
                                type: string
                            forwardCount:
                              type: integer
                              description: 转发次数
                            contact:
                              type: object
                              properties:
                                username:
                                  type: string
                                  description: username
                                nickname:
                                  type: string
                                  description: 昵称
                                headUrl:
                                  type: string
                                  description: 头像
                                seq:
                                  type: integer
                                signature:
                                  type: string
                                  description: 简介
                                followFlag:
                                  type: integer
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
                                      description: 国家
                                    province:
                                      type: string
                                      description: 省份
                                    city:
                                      type: string
                                      description: 城市
                                    sex:
                                      type: integer
                                      description: 性别
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
                                  description: 扩展信息
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
                                friendFollowCount:
                                  type: integer
                                oneTimeFlag:
                                  type: integer
                                status:
                                  type: integer
                              required:
                                - username
                                - nickname
                                - headUrl
                                - seq
                                - signature
                                - followFlag
                                - authInfo
                                - coverImgUrl
                                - spamStatus
                                - extFlag
                                - extInfo
                                - liveStatus
                                - liveCoverImgUrl
                                - liveInfo
                                - friendFollowCount
                                - oneTimeFlag
                                - status
                              x-apifox-orders:
                                - username
                                - nickname
                                - headUrl
                                - seq
                                - signature
                                - followFlag
                                - authInfo
                                - coverImgUrl
                                - spamStatus
                                - extFlag
                                - extInfo
                                - liveStatus
                                - liveCoverImgUrl
                                - liveInfo
                                - friendFollowCount
                                - oneTimeFlag
                                - status
                              description: 作者信息
                            displayid:
                              type: integer
                            likeCount:
                              type: integer
                              description: 点赞数
                            commentCount:
                              type: integer
                              description: 评论数
                            deletetime:
                              type: integer
                            friendLikeCount:
                              type: integer
                              description: 好友点赞数
                            objectNonceId:
                              type: string
                              description: 对象NonceId
                            objectStatus:
                              type: integer
                            sendShareFavWording:
                              type: string
                            originalFlag:
                              type: integer
                            secondaryShowFlag:
                              type: integer
                            sessionBuffer:
                              type: string
                            favCount:
                              type: integer
                              description: 收藏数量
                            urlValidTime:
                              type: integer
                            forwardStyle:
                              type: integer
                            permissionFlag:
                              type: integer
                            attachmentList:
                              type: object
                              properties: {}
                              x-apifox-orders: []
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
                            tipsInfo:
                              type: object
                              properties: {}
                              x-apifox-orders: []
                            internalFeedbackUrl:
                              type: string
                            ringtoneCount:
                              type: integer
                            funcFlag:
                              type: integer
                            playhistoryInfo:
                              type: object
                              properties: {}
                              x-apifox-orders: []
                            flowCardRecommandReason:
                              type: object
                              properties: {}
                              x-apifox-orders: []
                            ipRegionInfo:
                              type: object
                              properties: {}
                              x-apifox-orders: []
                          x-apifox-orders:
                            - id
                            - nickname
                            - username
                            - objectDesc
                            - createtime
                            - likeList
                            - forwardCount
                            - contact
                            - displayid
                            - likeCount
                            - commentCount
                            - deletetime
                            - friendLikeCount
                            - objectNonceId
                            - objectStatus
                            - sendShareFavWording
                            - originalFlag
                            - secondaryShowFlag
                            - sessionBuffer
                            - favCount
                            - urlValidTime
                            - forwardStyle
                            - permissionFlag
                            - attachmentList
                            - objectType
                            - followFeedCount
                            - verifyInfoBuf
                            - wxStatusRefCount
                            - adFlag
                            - tipsInfo
                            - internalFeedbackUrl
                            - ringtoneCount
                            - funcFlag
                            - playhistoryInfo
                            - flowCardRecommandReason
                            - ipRegionInfo
                      finderUserInfo:
                        type: object
                        properties:
                          coverImgUrl:
                            type: string
                        required:
                          - coverImgUrl
                        x-apifox-orders:
                          - coverImgUrl
                      contact:
                        type: object
                        properties:
                          username:
                            type: string
                            description: username
                          nickname:
                            type: string
                            description: 昵称
                          headUrl:
                            type: string
                            description: 头像
                          signature:
                            type: string
                            description: 简介
                          followFlag:
                            type: integer
                          followTime:
                            type: integer
                            description: 关注时间
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
                                description: 国家
                              province:
                                type: string
                                description: 省份
                              city:
                                type: string
                                description: 城市
                              sex:
                                type: integer
                                description: 性别
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
                            description: 扩展信息
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
                          friendFollowCount:
                            type: integer
                            description: 好友关注数
                          oneTimeFlag:
                            type: integer
                          status:
                            type: integer
                        required:
                          - username
                          - nickname
                          - headUrl
                          - signature
                          - followFlag
                          - followTime
                          - authInfo
                          - coverImgUrl
                          - spamStatus
                          - extFlag
                          - extInfo
                          - liveStatus
                          - liveCoverImgUrl
                          - liveInfo
                          - friendFollowCount
                          - oneTimeFlag
                          - status
                        x-apifox-orders:
                          - username
                          - nickname
                          - headUrl
                          - signature
                          - followFlag
                          - followTime
                          - authInfo
                          - coverImgUrl
                          - spamStatus
                          - extFlag
                          - extInfo
                          - liveStatus
                          - liveCoverImgUrl
                          - liveInfo
                          - friendFollowCount
                          - oneTimeFlag
                          - status
                        description: 用户信息
                      feedsCount:
                        type: integer
                      continueFlag:
                        type: integer
                        description: 是否可以翻页 是:1
                      lastBuffer:
                        type: string
                        description: 翻页的标识，请求翻页时会用到
                      friendFollowCount:
                        type: integer
                        description: 好友关注数
                      userTags:
                        type: array
                        items:
                          type: string
                      preloadInfo:
                        type: object
                        properties:
                          preloadStrategyId:
                            type: integer
                          globalInfo:
                            type: object
                            properties:
                              prevCount:
                                type: integer
                              nextCount:
                                type: integer
                              maxBitRate:
                                type: integer
                              preloadFileMinBytes:
                                type: integer
                              preloadMaxConcurrentCount:
                                type: integer
                              megavideoMaxBitRate:
                                type: integer
                              megavideoPrevCount:
                                type: integer
                              megavideoNextCount:
                                type: integer
                              minBufferLength:
                                type: integer
                              maxBufferLength:
                                type: integer
                              minCurrentFeedBufferLength:
                                type: integer
                              canPreCreatedPlayer:
                                type: integer
                            required:
                              - prevCount
                              - nextCount
                              - maxBitRate
                              - preloadFileMinBytes
                              - preloadMaxConcurrentCount
                              - megavideoMaxBitRate
                              - megavideoPrevCount
                              - megavideoNextCount
                              - minBufferLength
                              - maxBufferLength
                              - minCurrentFeedBufferLength
                              - canPreCreatedPlayer
                            x-apifox-orders:
                              - prevCount
                              - nextCount
                              - maxBitRate
                              - preloadFileMinBytes
                              - preloadMaxConcurrentCount
                              - megavideoMaxBitRate
                              - megavideoPrevCount
                              - megavideoNextCount
                              - minBufferLength
                              - maxBufferLength
                              - minCurrentFeedBufferLength
                              - canPreCreatedPlayer
                        required:
                          - preloadStrategyId
                          - globalInfo
                        x-apifox-orders:
                          - preloadStrategyId
                          - globalInfo
                      privateLock:
                        type: integer
                      liveDurationHours:
                        type: integer
                      justWatch:
                        type: object
                        properties:
                          showJustWatch:
                            type: integer
                          allowPrefetch:
                            type: integer
                        required:
                          - showJustWatch
                          - allowPrefetch
                        x-apifox-orders:
                          - showJustWatch
                          - allowPrefetch
                      ipRegionInfo:
                        type: object
                        properties: {}
                        x-apifox-orders: []
                        description: 地区信息
                      mcnInfo:
                        type: object
                        properties:
                          agencyName:
                            type: string
                        required:
                          - agencyName
                        x-apifox-orders:
                          - agencyName
                      productInfo:
                        type: object
                        properties: {}
                        x-apifox-orders: []
                    required:
                      - object
                      - finderUserInfo
                      - contact
                      - feedsCount
                      - continueFlag
                      - lastBuffer
                      - friendFollowCount
                      - userTags
                      - preloadInfo
                      - privateLock
                      - liveDurationHours
                      - justWatch
                      - ipRegionInfo
                      - mcnInfo
                      - productInfo
                    x-apifox-orders:
                      - object
                      - finderUserInfo
                      - contact
                      - feedsCount
                      - continueFlag
                      - lastBuffer
                      - friendFollowCount
                      - userTags
                      - preloadInfo
                      - privateLock
                      - liveDurationHours
                      - justWatch
                      - ipRegionInfo
                      - mcnInfo
                      - productInfo
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
                    - id: 14379133554206378000
                      nickname: 苏生-服务支持
                      username: >-
                        v2_060000231003b20faec8cae7811bcadcc904ef30b0770fd600f70cfec5c128fc2ef6421e0c7a@finder
                      objectDesc:
                        description: ''
                        media:
                          - Url: >-
                              http://wxapp.tc.qq.com/251/20304/stodownload?encfilekey=oibeqyX228riaCwo9STVsGLPj9UYCicgttvzDicPxtLUK1Mnwm6rYabzqqibT9LsSXMYSYPV0UVmiaibvf0e7scdaQV6ajtXpK6BgQoeUEuPy8ibSiaSy87VbhWianUWUrQGaloGMGiatejfdN5cT0&bizid=1023&dotrans=0&hy=SH&idx=1&m=aab40d3465073a9c29c4e171def00b7e&wxampicformat=500
                            ThumbUrl: >-
                              http://wxapp.tc.qq.com/251/20350/stodownload?encfilekey=WTva9YVXqXcSUicrMCercmDHmKYPBXC7ePV8OE7k7cAJaZDnHpwbibWib7qmricaWHFyR3GjKb7EibTiaLOiaDFZmgibqm0dMLHIKZz5EorAyY5ypTFjHDwdj92P0Un9fSibQDHQT8jUVINwuFSk&bizid=1023&dotrans=0&hy=SH&idx=1&m=40e334927eb1f7a5232afb0736776a76&picformat=200&wxampicformat=501
                            MediaType: 2
                            VideoPlayLen: 0
                            Width: 904
                            Height: 1224
                            Md5Sum: aab40d3465073a9c29c4e171def00b7e
                            FileSize: 0
                            Bitrate: 0
                            decodeKey: '881819874'
                            urlToken: >-
                              &token=6xykWLEnztLFU5qOA2qKKevOHYmbmCFUd4tVjKf7fwK6zfmcbIgdiaricVk3LbBTMNHW5Tlmebr6a1lg5mB05BxsVysyozZTHgXpISicGDjDzFsFhevODHvAyvnummjJMJwoVHIsHpnRF8s5hWicYaRQHEOC9Ajqf3xSBadW2ISpXV4&basedata=CAASACIAKgUImB0QAA&sign=EyWgHb1jPRldeC4pftH2J3M7JvuBpK2xfkMlw21vV8jOo4bdlZDd0HJnHvGBJYbe9x3DIxy2ZjSmavbSzJIO0A&ctsc=32
                            thumbUrlToken: >-
                              &token=Cvvj5Ix3eeyD0TVgRZ2eE3Qoj53ibu5gDMDk1YO8gHI1akBmtxpFWdBdJg69NOzUBsSHsjK22ibSmqLtTJURmRpgwxVgLcvSsOrSdqhXoYqS5y15ibnNCLkqpfPCeicDDveuShFO1Mj1UTzwHgUBbTyXtbF8icV1KEXgj&ctsc=1-32
                            codecInfo:
                              videoScore: 0
                              videoCoverScore: 0
                              videoAudioScore: 0
                              thumbScore: 0
                              hdimgScore: 0
                              hasStickers: 0
                              useAlgorithmCover: 0
                            hlsSpec: {}
                            hotFlag: 0
                            halfRect:
                              left: 0
                              top: 333
                              right: 904
                              bottom: 890
                            fullWidth: 0
                            fullHeight: 0
                            fullFileSize: 0
                            fullBitrate: 0
                            hdrSpec: {}
                            cardShowStyle: 0
                            dynamicRangeType: 0
                            videoType: 0
                            duplicateFileSize: 0
                        mediaType: 2
                        extra: {}
                        location:
                          longitude: 0
                          latitude: 0
                          poiClassifyType: 0
                        extReading: {}
                        feedLocation: {}
                        imgFeedBgmInfo:
                          docId: '78240202873186745'
                          albumThumbUrl: >-
                            http://wx.y.gtimg.cn/music/photo_new/T002R500x500M000002ZYHCj47dXDN_1.jpg
                          name: 满园春色惹人醉 (DJ版)
                          artist: DJRE
                          albumName: ''
                          mediaStreamingUrl: >-
                            http://wx.music.tc.qq.com/C400001MJxs61eCHGW.m4a?guid=2000000186&vkey=AA5B0E52406CF4995F71251A2058D95D14F5544C7F614F6C58C0D44AF02D9A98A743BE568DEDC9B1D96F80BCB07840884226AD5613FE56A2&uin=0&fromtag=30186&trace=0920fa4b25eaa560
                          musicPlayLen: 0
                          docType: 1
                          isTrySong: 0
                        followPostInfo:
                          musicInfo:
                            docId: '78240202873186745'
                            albumThumbUrl: >-
                              http://wx.y.gtimg.cn/music/photo_new/T002R500x500M000002ZYHCj47dXDN_1.jpg
                            name: 满园春色惹人醉 (DJ版)
                            artist: DJRE
                            albumName: ''
                            mediaStreamingUrl: >-
                              http://wx.music.tc.qq.com/C400001MJxs61eCHGW.m4a?guid=2000000186&vkey=AA5B0E52406CF4995F71251A2058D95D14F5544C7F614F6C58C0D44AF02D9A98A743BE568DEDC9B1D96F80BCB07840884226AD5613FE56A2&uin=0&fromtag=30186&trace=0920fa4b25eaa560
                            musicPlayLen: 0
                            docType: 1
                            isTrySong: 0
                          groupId: Listen_78240202873186745
                          hasBgm: 1
                        fromApp:
                          appid: ''
                          uiStyle: 0
                          extInfo: ''
                          source: 0
                          sdkExtInfo: ''
                        event:
                          eventTopicId: 0
                          eventName: ''
                          eventCreatorNickname: ''
                          eventAttendCount: 0
                          hiddenMark: 0
                        draftObjectId: 0
                        clientDraftExtInfo:
                          waitType: 0
                        generalReportInfo: {}
                        posterLocation:
                          city: Xuzhou City
                        finderNewlifeDesc: {}
                      createtime: 1714126295
                      forwardCount: 2
                      contact:
                        username: >-
                          v2_060000231003b20faec8cae7811bcadcc904ef30b0770fd600f70cfec5c128fc2ef6421e0c7a@finder
                        nickname: 苏生-服务支持
                        headUrl: >-
                          https://wx.qlogo.cn/finderhead/ver_1/xV2hVfZ8cDEjCT2zGUBWSLYasZn8YuaHicLiagteZG0QI3Biby83nlPb7EFHEk4RA9zb8VZXGn6xaMgJgI6lPIB7ogDI5CiaPLzgccaeyqQ48V3EBl4tGXhZ9UKwOqvw5ubv/0
                        seq: 1
                        signature: videosapi技术支持
                        followFlag: 0
                        authInfo: {}
                        coverImgUrl: ''
                        spamStatus: 0
                        extFlag: 262156
                        extInfo:
                          country: CN
                          province: Jiangsu
                          city: Xuzhou
                          sex: 1
                        liveStatus: 2
                        liveCoverImgUrl: ''
                        liveInfo:
                          anchorStatusFlag: 2048
                          switchFlag: 119263
                          micSetting: {}
                          lotterySetting:
                            settingFlag: 0
                            attendType: 4
                        friendFollowCount: 1
                        oneTimeFlag: 2
                        status: 0
                        clubInfo: {}
                      displayid: 14379133554206378000
                      likeCount: 1
                      commentCount: 6
                      deletetime: 0
                      objectNonceId: '11171020040813205610_0_32_2_2_1742215089869280'
                      objectStatus: 0
                      sendShareFavWording: ''
                      originalFlag: 0
                      secondaryShowFlag: 1
                      sessionBuffer: >-
                        eyJjdXJfbGlrZV9jb3VudCI6MSwiY3VyX2NvbW1lbnRfY291bnQiOjYsInJlY2FsbF90eXBlcyI6W10sImRlbGl2ZXJ5X3NjZW5lIjoyLCJkZWxpdmVyeV90aW1lIjoxNzQyMjE1MDkwLCJzZXRfY29uZGl0aW9uX2ZsYWciOjksInJlY2FsbF9pbmRleCI6W10sInJlcXVlc3RfaWQiOjE3NDIyMTUwODk4NjkyODAsIm1lZGlhX3R5cGUiOjIsImNyZWF0ZV90aW1lIjoxNzE0MTI2Mjk1LCJyZWNhbGxfaW5mbyI6W10sInNlY3JldGVfZGF0YSI6IkJnQUFXSkhudzNkZkxTTDdLaXMxdjlMSXJack8xWStQc1NkVEpNbDBRZ1FYd04wRmU1TStjK2hIZlwvYlV5dENZcFFRZ1g3Mk15em89Iiwib2ZsYWciOjE2ODA5OTg0LCJ0YWJfc2Vzc2lvbl9pZCI6MTc0MjIxNTA4OTg4ODA2NiwiaWRjIjozLCJkZXZpY2VfdHlwZV9pZCI6MTMsImRldmljZV9wbGF0Zm9ybSI6ImlQYWQxMyw4IiwiZmVlZF9wb3MiOjAsImNsaWVudF9yZXBvcnRfYnVmZiI6IntcImlmX3NwbGl0X3NjcmVlbl9pcGFkXCI6MCxcImVudGVyU291cmNlSW5mb1wiOlwie1xcXCJmaW5kZXJ1c2VybmFtZVxcXCI6XFxcIlxcXCIsXFxcImZlZWRpZFxcXCI6XFxcIlxcXCJ9XCIsXCJleHRyYWluZm9cIjpcIntcXFwicmVnY291bnRyeVxcXCI6XFxcIkNOXFxcIn1cIixcInNlc3Npb25JZFwiOlwiU3BsaXRWaWV3RW1wdHlWaWV3Q29udHJvbGxlcl8xNzQyMjE1MDgxMTI3IyQwXzE3NDIyMTUwNjg0OTEjXCIsXCJqdW1wSWRcIjp7XCJ0cmFjZWlkXCI6XCJcIixcInNvdXJjZWlkXCI6XCJcIn19IiwiY29tbWVudF9zY2VuZSI6MzIsIm9iamVjdF9pZCI6MTQzNzkxMzM1NTQyMDYzNzgwMTksImdlb2hhc2giOjMzNzc2OTk3MjA1Mjc4NzIsInRhYl9mZWVkX3BvcyI6MCwiZW50cmFuY2Vfc2NlbmUiOjIsImNhcmRfdHlwZSI6MywiZXhwdF9mbGFnIjo4ODc4Nzk1NSwidXNlcl9tb2RlbF9mbGFnIjo4LCJpc19mcmllbmQiOnRydWUsImN0eF9pZCI6IjItMy0zMi0zN2ZmYmVhODlkNjBmMjUyZmIzMWM3NDYxMmY1YWVkNjE3NDIyMTUwODYyNTMiLCJhZF9mbGFnIjo0LCJlcmlsIjpbXSwicGdrZXlzIjpbXSwic2NpZCI6ImFmMGI3MmNhLTAzMmMtMTFmMC05ZjkyLWU1NjRkOTc0ZWQ4YiIsImNvbW1lbnRfdmVyIjoxNzQxMDg0MTc1fQ==
                      favCount: 1
                      urlValidTime: 172800
                      forwardStyle: 0
                      permissionFlag: 2147483656
                      attachmentList: {}
                      objectType: 0
                      followFeedCount: 0
                      verifyInfoBuf: >-
                        CsADCmEKVMZ6O/DNYthI2bQM8nH1rZrrcpBrLlchNG+IX4ZYcf3eNoowK6PJIMGByiLmDBv/UXK8Ti8akeXKC+IC0L/4gEMHT89PoRpkbXcxElP33Vl3NzFRi7ypu9ktDrUoaoOyvQZkG5ULGxLXUI3BsaPHWRD8bSRTCskzNKaSmnsW3qoY0LsloureX9Dj4fLu7PsmiuSezrJy3UFS08HvWzRmVtqZlg8Dd0iR8C5bXlACEOZTQWo0oh7p+Wg/BKIAF0RdOX/nvyJVmL9VfLbnj/deNnnz45k1EBEeYoZJ6cGBHZPSry+4FD8B1hfqCpxxd7ryMOsndbU1KxYxksdhIiqOzpo5Vmm16lmUDSPmRvnnCL5IR/PpBzKgCFzHam1IPvDoEokwQCZqqz2kJdD5f7lEarbEBFSyQPBoDGJ7jCC8PbEPFJtiJo3dzl3SRoDsadKioPsJTx1bUfJFGrJw+oiWswcvfhgOBUOKkVeBQg1Z43p5TeX3ffUNCarjLx1reS1MqV+G5VbotBeHgGqgRYd5e2rKQx23HE7MjNGJ8y4rppGukYwOPeCKGWCqM5GqxITZAP3+NLxCj83LuEnmOA==
                      wxStatusRefCount: 0
                      adFlag: 4
                      tipsInfo: {}
                      internalFeedbackUrl: ''
                      ringtoneCount: 0
                      funcFlag: 256
                      playhistoryInfo: {}
                      finderPromotionJumpinfo: {}
                      flowCardRecommandReason: {}
                      ipRegionInfo: {}
                  finderUserInfo:
                    coverImgUrl: ''
                  contact:
                    username: >-
                      v2_060000231003b20faec8cae7811bcadcc904ef30b0770fd600f70cfec5c128fc2ef6421e0c7a@finder
                    nickname: 苏生-服务支持
                    headUrl: >-
                      https://wx.qlogo.cn/finderhead/ver_1/xV2hVfZ8cDEjCT2zGUBWSLYasZn8YuaHicLiagteZG0QI3Biby83nlPb7EFHEk4RA9zb8VZXGn6xaMgJgI6lPIB7ogDI5CiaPLzgccaeyqQ48V3EBl4tGXhZ9UKwOqvw5ubv/0
                    signature: videosapi技术支持
                    followFlag: 0
                    authInfo: {}
                    coverImgUrl: ''
                    spamStatus: 0
                    extFlag: 262156
                    extInfo:
                      country: CN
                      province: Jiangsu
                      city: Xuzhou
                      sex: 1
                    liveStatus: 2
                    liveCoverImgUrl: ''
                    liveInfo:
                      anchorStatusFlag: 2048
                      switchFlag: 119263
                      micSetting: {}
                      lotterySetting:
                        settingFlag: 0
                        attendType: 4
                    oneTimeFlag: 2
                    status: 0
                    clubInfo: {}
                  feedsCount: 1
                  continueFlag: 0
                  lastBuffer: >-
                    CKOQ/OKJubzGxwEQARgAIKOQ/OKJubzGxwEwADjCtrj8kJGMA0CAwJPy+IyPA0ijkPziibm8xscB
                  userTags:
                    - 55S3
                    - 5rGf6IuPIOW+kOW3ng==
                  preloadInfo:
                    preloadStrategyId: 2381702531
                    globalInfo:
                      prevCount: 0
                      nextCount: 5
                      maxBitRate: 150
                      preloadFileMinBytes: 0
                      preloadMaxConcurrentCount: 1
                      megavideoMaxBitRate: 150
                      megavideoPrevCount: 1
                      megavideoNextCount: 2
                      minBufferLength: 25
                      maxBufferLength: 30
                      minCurrentFeedBufferLength: 5
                      canPreCreatedPlayer: 0
                  liveDurationHours: 0
                  justWatch:
                    showJustWatch: 0
                    allowPrefetch: 0
                  ipRegionInfo: {}
                  mcnInfo:
                    agencyName: 江苏
                  productInfo: {}
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/视频号模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454795-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
