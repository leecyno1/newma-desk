# (步骤1)获取登录二维码

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /login/getLoginQrCode:
    post:
      summary: (步骤1)获取登录二维码
      deprecated: false
      description: >-
        >  如果需要全局代理（即所有接口都走代理，可直接在调用的接口内增加" useProxy:true
        "字段。useproxy字段默认为false不单独展示在各个接口内）但是有可能会影响接口的实时响应速度


        - 地区ID仅供测试，如需正常使用业务建议自行购买干净代理ip。
      tags:
        - 核心 API 模块/登录模块
        - 基础API/登录模块
      parameters:
        - name: VideosApi-token
          in: header
          description: PS：API后台-点击访问控制-生成Token
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
                  description: |-
                    设备ID/appId
                    首次登录：请传空值，系统会自动触发并创建新设备。
                    二次登录：取码时必须传入首次接口返回的 appId。
                    ⚠️ 风控警告：请在业务逻辑中做好状态管理。同一个账号务必避免重复创建设备，否则极易触发官方风控机制导致封号或异常。
                  additionalProperties: false
                proxyIp:
                  type: string
                  description: |-
                    代理IP
                    格式：socks5://username:password@123.2.2.2
                  additionalProperties: false
                regionId:
                  type: string
                  description: >-
                    地区ID

                    若目前支持的regionId中没有您所在的地区，可以自行采购socks5协议代理IP，填写到proxyIp参数中，地区ID在前，地区在后
                      ```java HelloWorld.java
                    110000*北京市|120000*天津市|130000*河北省|140000*山西省|150000*内蒙古

                    210000*辽宁省|220000*吉林省|230000*黑龙江

                    310000*上海市|320000*江苏省|330000*浙江省|340000*安徽省|350000*福建省|360000*江西省|370000*山东省

                    410000*河南省|420000*湖北省|430000*湖南省|440000*广东省|450000*广西省|460000*海南省

                    500000*重庆市|510000*四川省|520000*贵州省|530000*云南省|540000*西藏自治区

                    610000*陕西省|620000*甘肃省|630000*青海省|640000*宁夏自治区|650000*新疆自治区
                      ```
                  additionalProperties: false
                type:
                  type: string
                  description: 设备类型：ipad / mac
                ttuid:
                  type: string
                  description: >-
                    代理本机ID，需配合 regionId/proxyIp
                    使用，不单独使用。可临时借用用户的本地网络取码有50%概率跳过ipad验证。

                    [代理TTUID点击下载](https://wechatapi-static.oss-cn-qingdao.aliyuncs.com/ttuid.rar)
              x-apifox-orders:
                - appId
                - proxyIp
                - regionId
                - type
                - ttuid
              required:
                - regionId
                - type
            example:
              appId: ''
              proxyIp: ''
              regionId: '{{regionId}}'
              type: mac
              ttuid: ''
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
                      qrData:
                        type: string
                        description: 二维码内包含的信息
                      appId:
                        type: string
                        description: 设备ID，需传至执行登录接口
                      qrImgBase64:
                        type: string
                        description: 登录二维码图片base64
                      uuid:
                        type: string
                        description: 二维码的uuid
                      qrUrl:
                        type: string
                        description: 二维码直接打开地址
                    required:
                      - qrData
                      - qrImgBase64
                      - uuid
                      - appId
                      - qrUrl
                    description: 响应数据
                    x-apifox-orders:
                      - qrData
                      - qrUrl
                      - appId
                      - qrImgBase64
                      - uuid
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
                  qrData: http://weixin.qq.com/x/oaX6Iz_9w8hiLhJyXQim
                  qrUrl: >-
                    http://api.asilu.com/qrcode/?t=http://weixin.qq.com/x/oaX6Iz_9w8hiLhJyXQim&size=250
                  qrImgBase64: >-
                    data:image/jpg;base64,iVBORw0KGgoAAAANSUhEUgAAALkAAAC5CAYAAAB0rZ5cAAAOf0lEQVR4Ae3BwXEry5JEwRNtUCdKfzmSAsXss7FIKwLv8veUu4DwRyQRjaQwkET8A5JCk0Q0kkKTRDSSQpNEfJCksCmJGJAU/oiXbf4y2/xltpmwzYRtvs0232abv+Li4ODRLg4OHu3i4ODRXrxRVXzbWou/QlIYSCKaqqKTFJokfJukMGCbrqro1lp8UlXxbWstuhfvie8Lf4RtfkE0tsOd+DLb/IK4C58lvi80FwcHj3ZxcPBoFwcHj/ZiSFLYlERsqip2SQpNEtFUFd1aiwlJoUlCJyk0ScSApNAkEU1V8W2SQpNEbJIUNiURAy+GbPOPiE22GRJ3YcA2b4jGdthkmyHxZbb5JNt828XBwaNdHBw82sXBwaO9+OMkhSaJGKgqOklhwDYTVcVEVdFJCk0SJiSFJokYkBQGbPMEL/442/yCaGyHzxIzorEd7sSA7bDJNv+fXBwcPNrFwcGjXRwcPNqL/0GSwibbdFXFLklhIIloqopOUmiSiAFJYcA2XVXRrbV4ghf/g2zzYWKTbX5BNLbDJtv8grgLD3BxcPBoFwcHj3ZxcPBoL4aqir+sqphYa7FLUmiS0K216CSFJoloqoqJqmLXWotOUmhs821Vxbe9mBN/m5gJm2zzhrgLjW2GxIzYFxrb/CPiyy4ODh7t4uDg0S4ODh7txRuSwpfZZldV0UkKTRKxSVJoktBJCk0SurUWE5JCk0Q0kkKTRDSSQpOEbq1FV1V0ay12SQpfZpvuxRu2+eNEYzt8kG3eEI3tcCfuwoBtJmwzYZs3xF24E3dhk23+hYuDg0e7ODh4tIuDg0d7VRV/WVWxS1JoktBJCk0SOkmhsU0nKTS22SUpNLbpJIXGNp9UVUxUFX/FCxB/m9hkmzdEYzvcicZ2GLDNJ9lmwjb/ATEj/oiLg4NHuzg4eLSLg4NHe/ELkkKTRAxICk0SsamqmJAUGtt0kkKThG6txSdVFRNrLbqqYkJSaGzTSQpNErFJUtiURDSSwsCLX7DNLtt8mBiwHQZs84a4C58lZsKdGLAdBmzzSbb5JNtMXBwcPNrFwcGjXRwcPJqS8AuhkUSXRNyFOzEgKQwkEXdhkyS6JHRrLbqqopPELtt0Pz8/TNimqyq6tRbdz88PE0nEXRhYa9H9/PzQ2Wbixe+IxnaYEZts8wtik+1wJ+7CnWhshw+yzS+Iu9DY5hfETGhss+vi4ODRLg4OHu3i4ODRXpLCB9lmQlJokohGUmiS0K21mJAUmiRik6TQJGGiqujWWnRVxa61Fl1VMVFV7JIUNiVh11qL7mWbf8E2E7Z5Q9yFAdt8km3eEDPiLtyJfeFOzIhNtsM+sS80FwcHj3ZxcPBoFwcHjybbYaCq6NZadFVFJ4kuCZ0kOtt0VSXuwp24C3eikRQa20z8/PwwkUTchTvRSApNEtGstULz8/NDl0Q0kkKTRMyEZq1FV1W8IfaF5sWcuAt3orEd7kRjO+wTM2LANrts8wtiwDa7bDNhm18Qd+FOfJZoLg4OHu3i4ODRLg4OHu3Ff6Cq6CSFxjYTkkKTRAxICgNJmFhr8UmSQpNEDEgKTRK6tRbfJik0tukkhSaJ+KAX/w3R2A6bbLPLNkNiJnyQbXbZ5g1xF77MNhO2+baLg4NHuzg4eLSLg4NHe/FGVdFJCk0SOklhIAm71lp0ksJAErq1Fp2k0CQRTVUxsdaikxSaJExUFd9WVXxbVdFJCk0S0UgKAy/eE43tcCca22FG7AuNbYbEXWhsMyRmQmObN8SM+D7xfaKxHQZsM3FxcPBoFwcHj3ZxcPBoL4aqiomqYkJS2GSbiaqikxSaJPwVksIHJREDkkKTRAxICo1tdlUVnaTQJKFba9G9mBMzYsB2+D7R2A534o+wzb9gm122+TDR2A534i40FwcHj3ZxcPBoFwcHj/ZiSFIYSCIGqopday2+TVJokohGUmiSiH+gqugkhcY2E5JCk0Q0VcXEWotdVUUnKTRJ6F4M2ebDxL7wZbaZsM0fIhrbYZNthsRM2Cca2+FONBcHB492cXDwaBcHB4/2qio6SaGxzYSk0CQRjaTQJBF/mKTQ2KaTFBrbdFXFxFqLrqroJIXGNl1VMbHWYkJSGEjChKQwkISJFyAa22GTbSZs87/GNhO2GRIz4U40tsOMmAkDthkSA7YZEgMXBwePdnFw8GgXBweP9mKoqphYazFRVXSSwkAS/rKqoltr8W1VRbfWYkJSaJLQSQqNbXZJCo1tdkkKzYs5MRNmRGM7zIi/TdyF7xN3YcA2b4jGdvgg23ySbbqLg4NHuzg4eLSLg4NHe0kKTRI6SaFJIjZJCo1tJiSFgSSiqSomqopdkkKThAlJobHNrqqikxSaJOyqKnZVFd1aiwlJobFN97LNG6KxHT7INrts8wtiRmyyHe7EgG0+TDS2w53YJ/aJuzBgm4mLg4NHuzg4eLSLg4NHe1UVuySFJgkTVUW31mJXVdFJCk0S0UgKm5KIL6sqOklhUxI6SaFJIpqqopMUmiSikRQGktCtteiqim6tRfcCxCbbvCFmxF3YJxrbYcA2f5xobId9orEdZkRjOwzYZkjchTtxF5qLg4NHuzg4eLSLg4NHezFUVXRrLTpJoUkiGkmhSUK31qKrKj6pqujWWnRVRScpNEmYkBQa23SSQpOEXZJCk4ROUhiwTScpNLbZVVV0kkKThO7FnLgLjW0mbPOGuAt34rPEXbgTje1wJwZsM2GbN8Qm2+FONLbDJtt8mGhshzvRXBwcPNrFwcGjXRwcPNqLX6gqJiSFJgm7JIUmiWiqik+SFJokTEgKTRK6tRYTkkKTRDSSQpOETlJokrBrrUVXVeySFBrbdJJC8+J3xIDtcCc22WZIfJBt3hADtnlD3IUB20zY5g3R2A53Yl+4E5tsM2Gb7uLg4NEuDg4e7eLg4NFevCEpNElEIyk0ScSApDCQhE+SFJokoqkqurUWnaQwYJtOUmiSMLHWYpek0NhmQlJokoimqugkhU222fXiDdtM2GaXbYbEB9lmSNyFxja7bPOGmAmbbLPLNkOisR3+gYuDg0e7ODh4tIuDg0d7SQqNbXZJCo1tuqpiQlJokogBSaFJQicpDNhmoqro1lrskhSaJExUFd1ai66q+CRJoUlCt9aiqyo+6WWbT7LNkBiwHTbZ5g3R2A6fJe7CJtu8IWbEXbgTH2SbN8RduBMfdHFw8GgXBwePdnFw8GgvPqyqmJAUmiTig6qKiapiYq3FhKTQJKFba7FLUthkmwlJoUlCJyk0tpmoKr7txeeJAdvh+8SMmAkDtnlD3IVNtvk227whGtthn/iyi4ODR7s4OHi0i4ODR3tVFd1ai12SQpNENFVFJyk0SdglKXxQEibWWnSSQpOEf6Gq+KSqoltr0UkKTRLRSApNEjEgKTQvQNyFTbYZEo3tcCc22ebDxExobPOG+DfEZ4m70Nhmwja7bNNdHBw82sXBwaNdHBw82ktSaJIwUVV0ay06SWEgCZ2ksCkJ3VqLv0JSGEhCt9aiqyq6tRYTkkKThAlJoUnCJ0kKTRIx8LLNG2JG3IXGNkOisR32ibvwR9hmSNyFO3EXBmzzhhiwzRvig2yz6+Lg4NEuDg4e7eLg4NFeVUUnKTRJxAdVFZ2k0NhmoqrYVVV0ay06SWEgCd1ai4mqYqKq2CUpNLbpJIUmiRiQFJokopEUmiR80gsQje3wfaKxHfaJfeIuNLYZEndhRsyITbaZsM0u20zY5g3xQRcHB492cXDwaBcHB4/2khQa23SSwkASurUWnaTQJOGTJIXGNhNVxcRai05SaGzTVRWdpNAkEY2kMJCEXWstOkmhsc2EpNDYZpek0CShe9lmwjZD4i40tnlDfJBtfkHMhMY2Q6KxHQZsMyT2hcY2u2zzSbZ5QzQXBwePdnFw8GgXBweP9qoqvq2q2CUpbEpCt9aikxSaJOKDqoqJqqKTFBrbfJKk0NhmoqrYtdbikySF5gWI7xObbPML4i40tvkPiBnR2A5fZptfEPvCB9mmuzg4eLSLg4NHuzg4eLSXpPBHJBFNVfFJVUW31mJCUmiSsEtSaJKIpqr4tqpiYq3FhKTQJBGbJIXGNhMv2/xx4rPEXRiwzRtik22GxPeJmTBgm0+yza6Lg4NHuzg4eLSLg4NHe/FGVfFtay12SQoflISJqmJCUmiSiKaqmJAUBpKIRlJokohGUmiSiE1VxbdVFRMv3hPfFzbZ5sPEjBiwzZAYsM0u20zY5sPE94mBi4ODR7s4OHi0i4ODR3sxJClsSiK+rKro1lpMSApNEtFICgO26SSFgSSiqSomJIXGNp2k0CRhl6SwyTadpNAkoZMUmiSieTFkmz9O3IUB20zYZpdtfkEM2A4DtnlDbLLNJ9nmDdHYDgMXBwePdnFw8GgXBweP9uKPkxSaJHSSQmObT6oqJtZadFVFt9aikxSaJGJTVbFLUmhsM1FVdGstJqqKTlJobNNJCs2LP842b4jGdvg+MRPuxF1obPNhYpNtfkHchRnR2A4DtukuDg4e7eLg4NEuDg4e7cUfV1Xsqiom1lp0kkKTRDSSQpOEiaqiW2sxISk0SZiQFAZs01UVu6qKbq3FrqqiW2vRvfj7xD4xExrbTNjmDTEj7sKAbd4QA7b5BbFP3IV94i40FwcHj3ZxcPBoFwcHj/ZiqKr4KySFxjadpNAkEQNVxS5JYVMSJqqKCUmhsU1XVXRrLTpJoUkiNlUVnaTQJGGiquhezIk/wjYTtvkFsck2vyBmxIBthsRdaGzzYaKxHe7EjGguDg4e7eLg4NEuDg4e7cUbksKX2ebbqopOUmiS0EkKA0no1lp0VUW31mJCUmiSiEZSaJLQrbWYqCq6tRadpLApiWiqiglJYeDFG7Z5CNHYDneisR1mxF24E3dhwDYTtnlD3IUZcRca23yYGLDNxMXBwaNdHBw82sXBwaP9H6GgsODhgxLcAAAAAElFTkSuQmCC
                  uuid: oaX6Iz*****LhJyXQim
                  appId: wx_ZmxPv*******TB1d35N5r
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/登录模块
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454693-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
