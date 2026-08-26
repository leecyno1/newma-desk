# 创建微信群

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /group/createChatroom:
    post:
      summary: 创建微信群
      deprecated: false
      description: |-
        创建微信群时最少要选择两位微信好友
        邀请企微好友需要使用username
      tags:
        - 核心 API 模块/群管理接口
        - 基础API/群模块
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
                wxids:
                  type: array
                  items:
                    type: string
                    description: 好友的wxid
                  description: 好友的wxid列表
                  minItems: 2
              x-apifox-orders:
                - appId
                - wxids
              required:
                - appId
                - wxids
            example:
              appId: '{{appid}}'
              wxids:
                - wxid_**********
                - wxid_**********
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
                      headImgBase64:
                        type: string
                        description: 群头像的base64图片
                      chatroomId:
                        type: string
                        description: 群ID
                    required:
                      - headImgBase64
                      - chatroomId
                    x-apifox-orders:
                      - headImgBase64
                      - chatroomId
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
                      headImgBase64: >-
                        /9j/**********/2wBDAAMCAgMCAgMDAwMEAwMEBQgFBQQEBQoHBwYIDAoMDAsKCwsNDhIQDQ4RDgsLEBYQERMUFRUVDA8XGBYUGBIUFRT/2wBDAQMEBAUEBQkFBQkUDQsNFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBT/wAARCACLAIsDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwD77oooqyAooooAzvEOuQeG9GudSuY5ZYIACyQgFzlgOASB39a8v1/9qPwp4dtDc3VhrDRgZzHDEfw5lFdr8VDjwFqvJHEfTr/rUr87fi1q2o3umtoN3bzwlrxmWZTglSTiuulQ9rCUk9iJVFSknNaM+y/DH7YPgvxVcSQWthrcMidp4IRn6YlNdknxt0J1Vvs1+qk4yY4//i6+NI/g7qngf4c6V4zs2QNEFwo5aYHg5/DP5V5x4++OdxYiCJLp7JQ7sHY4djzwCOwrCcVyLkfvLc9ClCnUle3uvb9T7j8Q/td+D/Dc80dxpmuzLF1lgt4Sp+mZQf0p2nftdeC78WrPZ6xZx3H3ZLiGHCj1YLKxA/CvyV8V/GzxZqcX2Jbq4KiVm83O1iCSRznmrvwu+I+q6HqZvJLxGu5BhvP+ZCO55rHlm1odiw9GVScEttj92dB0n/hJdItdT0+7trizuoxLE4ZvmUjI7VePhC9C58yD6bjn+VfF/wCxb+2Hay3lh4M1ydY4JR5VtIGyEcYG3PpX6AsA+CCCMdaE7nmVabg0jyp7sxa/qGkvBKstmkUjTFR5UgfdjYc5ONhzkDqOtWK1PEkMseqsztuQoqKSO4zn+YrLoV7ambVnYKKKKokKKKKACiiigAooooA4n4zTm2+G2ryDHBgzk448+MGvnXxH4W0zxo1lHeaXK+xf9dvJPTIxx9K98/aB1GDSfhFr13cnEEX2dm4z/wAvEeP1xWN8E9SsPE/hnTtRt5UMZUlRKNxzyp/rXJXq1KdvZvff0PXwdKlWpyjUXp6nCfDrWH1j4X32gzWC3EFo0zRSS9HCT7NvTsOv0r83/wBpvX4dW8d38FlbQ2xhufIjjiHGefmHHX/Gv1f+JNzovhHQJbS1EUMkgflAFVGZt7H6k5596+NNL/Zl0b4i/G6xv/mWxllE7iNN0YfaWP5nJrGFRRbnfc9BU404KCWx5T8Df2UpPFjxah4qvPs1pKilYHb55MjrivZdf/Yi+HdpYyM15c2W5cx+bIWyfb0r2PxH8NNX0vxHHb6T4ds7yw383c10QwX/AGfk/Su11H4bXD6CPsN2tpc44m6qp9KTrzvodipU4W7s/OpPg/4h+FvxY0S10qc3VlfzbbSdWYFSGU4bjrX7ieB7m9vPCOlXGoBVvpLdGmB/v45Oa+StS8BLF8PpYdWuv7S1CzdbqK43YZGAI4bsOa6PwZ8S9atPB1ha3Opg3NmggZg3BAHBJrrjVg43R4+NoyUrI+gvGKqJLZhjcd+cfhXO1w/w58dv4zvdZjku/tT2ZiBxJuC7t/5fdruKuEuePMjxpXT1CiiitCQooooAKKKKACiiigDzv9oKxj1L4P8AiG2lAZHSHIPtPGf6V5D+zV4au4fhhOZrp4dt5ILbaP4AT/WvdfiqllL4C1NNRMgs2MSuYRluZUxj8cVmQafaeHPC1pZWIIsYolcbxhiWGf5muLENLQ9nBSSi/U+b/jdfSR31nY6hO4t7t/LuX7lRkjHvwKt/BXV/+Ef1VILe6his4nPkSM/IGcYJ+nau0ksF8T+IjpsXh+LWLxW3xSOuQh7/ANa6K0/Ze0zxVeW+p6vcizltSxitdO+QZzyH6557VhToOpHQ3nW9nPmZR8Y+PLu3e5iimJTcSso+7tz1xXimt/tHaFp94yXfiy4nlRjE9vbcgMODxn1r33xt4FEdvI0EiF4U2GJRwVHoOx96+cJPhj4e/tmaWOOzUyTFmVlG8tnj+tKVCVM9jD4nD1oc1ToeqeHNam1rRQZJ2e2miwBIfvA4IJ+uK47xN4Z8QQJdXz6+dL0OPlIEhyWHv8w5r2bwV8IjrSaeZQI9NkfDRIPLdV7MH5/Diq/xN+Cer6Laapd2etSa1pDW2xbS7/1kKjoCe5/AdK0hQUIXieNXxEZVdNjjf2H9Xs9W1X4hm0unudjWG8yJsYZ+04yMn0NfVdfOH7Hvw1k+Hq+LGkdWN/8AZHCbNrpt87hjnn71fR9dtNNRSZ5Fdp1G0FFFFaHOFFFFABRRRQAUUUUAcr8T40l8F3av90z22f8AwIjrn9b1Da4hz8i/L/45XQfE9WfwXd7BlhPbNz7XEZNea63qRn1BgrAoXycf7teZinaSPdwMVKi/X/I9E+GNxpsWnXQt5jBqqktJ5WPmGeB+XP4VNP4tlt/EX2TzVLsu/wAwenfNeNXniRvDl1pMkUoNw9zlsN1BVhg/ga0rrXZbnVFuf9YYyUO08YzxXqYKa5LHmY+naoj22HTbbWwz5QK3BHdjVAfDfSY7wXSwqGU5PArE8NajBKilZTHKfuqX6GumOozQAecflPcd67210PPV0b9lFGkaiMbUA4Aqr4gKT2bh13RgEMPWqUGtZiYQ4ZvSs/W9W+z6VdXLOAqxlip9RWLk0tUXG7ehL4f01bBJTHb+TFIFKt/exn/H9a16yvDusvq1gox+4jAMZPfPX+QrVrkvfU2ne+oUUUUyAooooAKKyPE08dvYxtKwVfNAyfoa5jT9TtYdSMkcqD6mm1aPMZznyrTVnfUVhQ+LbBmKNIQZOiJV+e7tfsYnluo7aGPknOJcf4Vg6iSubU05xv17Ddf0WHxFpM+n3EksUU23LwkBxhgwwSCOoHauMX4JaOGJ/tLVST6yx/8AxutfT/GPh3W782+m6rHcXGfmV2BkA7n6VJqCPpjTG4cCN/uXRPFKSpzV5K44161L3Y6GVafBbw/bXIndru6cdPPdSAfwUV00PhPSreza3js41DdZP4q50XyyyA+ah981pJfW6KrTToEHvW0Yci91GU8Q5u8ncSL4e6dBJ5iT3StnIIdeP/Ha3l0+IQLExaQL3Y806y1SDVYBJbyCVI/3ZI7Ec4/UV+dXgXUD4h+HRtryHfbHTHgmjk4a34olVlA0hFVFc/Q6PRoYblZkeRWH8IIwf0qPVPD9tq1hc2kxkWOcFWKEBh9OK+Lvgb4LTwteyaVJcmV7iBLpN3uW4/Svam0ssgYpy5yTU+3lLRmqpcuqZ7bpOlQ6NZR2sDO0aAAGQgn9AKu18/vpHtVSXRXGTVpJbFODk7tn0XRXzPPp/lnDDmqUtnnOBzT0MHGzsfUtFfPfwttXj8f6Wx6Dzf8A0U9fQlIRxPxZ1q20Pw7az3UTzRvdrGFQ85KOf6GuE027g1pQ1rayJnjmu0+M2f8AhGbPaoY/bU6jP8D1yXhy9k0+NjMVjVV3HjqKwrycad+hFOEXWv17G5babB4Ps5tU19xZWcKMwdm5kx/dryzw144vfjALyXRIlj8Ph2je8vcyMxHVVAxjFeM/tLfH59VtrrSrRnFpk+UC3KA16L+zkNXHw28PyWsLG1Z3EpSQIpbjJIINeNzym7H0EMPGL53ocp8X/hPrPhWyn1fwtqVxA5H/ACyO1jnrx6V0f7P/AMXz4p0e60PxFfSz3VnvaNZDyyKB19a9In8NX+q+JTczPD9hwQ0ZQ+Yvt1/pXhvgXTrXw/8AGSW38sGaR5oSgHG1du7P5iulO6smY1qap+9NWR78utaNIfkvXUe61MuraQ+F/tAODwd3FRR6usAz5Nsy+hXmie/juZEf7JAOP7n/ANevbUnY+Ta13PSPhqtquiXX2SUTRm6Ylgc87E4/lXyZ4S8Kprt74k0mOIQC6gxLLjA+fOcenSvrP4aOH0O5IRIx9qbhBgfcSvBPh9p1zYePNVW4ddsscSqgHy8Ft3P4iuarJX949SjflRPqGiJoPxK8O3qgiGS3a1YDoSuMY/76r0lkL5EfBGOGHaqGoaMdUutPuGcf6NNvAx0HGf5VuKxMm4nIIAxisHOC2Z02k+hTltimM7c/SqU1qgjhDH96+ScdK2J4wzhivy1WbYsiuyE7QQKy9pIfLPsYN1ZRAZwxP1rHngXnAIrp7p96/cC8c1j3bKinKnJIHA96XtWHK+pb+HUITxvpp5/5af8Aop69xrxfwEAvjawTBDL5meP+mbV7RXXRlzRuYTVmcX8VUL6BaAIZFF4pYDsNj8/yrz/Vla40K73QvHKABEfUV694kvr7T7GOWwtUvJvNAaORcjbg8/nivMvjP401ceD9Q02zs7W01GWNSbkjAiAHPf3rkxs+WjJPyNsHR9pXvHc/N79otfsnxDvLFHGxGcYT2Ne6fsf/ABqtdV8F/wDCEy3cdleHE0Etw4Bcn+EZrwL4h+EJ7jXrqZdQN+0hP7w1p/s9+Bp7L4n6PPcS4WKVXCxnn8a4lONpcu+h9C8FiIVeeovdPuHV73UfDU1zqN7MLI+XiSB2+Zm/hIHp1rx34E2918RvitdeK5JPK0lRMJJD0BbH+Fel/EbSxqOny+QWnk+7lCSOPX868E+EGtX/AIZ0DX/DV3NNoPmFnF7ImFDDPGSKz96HvCjT+sS9nV2Pr+w0q318NNpl9banCvXyCCR+tRtozQzlWtpiw7Yr4m03xXrnhq3YWl7cwW87kB0b/WD1Fey/DP8Aav1nwrNb2upbb+zjOA0qjeF9K7qWaxT95HVi+Doxjz0Z3Pr34fQNb6LMrQtBmdiFccn5V5rx6wuLc3D3a8EwB9w9817L4E+KGn/FnQ/7Y02MRRQyG1dQMfOFVj+jivnO11tF4yMdMV01qkavLNbM+ap0Hhpyo1N0en22oRqQhPA4FbtpdW7AcZNeTweI1DD5v1rYsPFaxyoS4UZ5+lcFWyeh2pK2h6gzwNGP3dZt4FUcLxWNrPjqwaC3Sy3I38TGucu/GAYH58/jWXPIiUZG/fSJu544rEuJljfIOSCOtY0/iRJTln6cdapTeIISCNw/OtE7rUVlbU7b4dTNJ43tC5yWaTH/AH7avba+ePhZqsd18QtLjVslvN/9FPX0PXpYf4H6nn1rc2hqeHImmvnUKrDyyTuHQZFfN37ZctxpNi4hIhW8+Vtg655b9a+l/CQLak47eUc/mK+ff26dOdfDGl3aIWMc5U4HY5P9K58fFOiz1Mlt9bd0fnpfo32mVQxwnT3rf+F0N2/xB0Q2sayOsytsZsA/Xmq15Yf6aSRw1dx8LfAl7rmrQ6jp19Haz6bMsjRFTl1/yK8DC6y1P1DMoNUIu2lj6ok06bTNf02zuYlklu4zkoQVUrjI/UV5x+0t8OLu70G9uLFo0Hmec0KgAn2GOcV9DaNo8WqSWd7KB5y/NvAPVsbv5Cn+NfCUDajFcywNdxY/1GOH+tfUvCuULn5O8c1Nps/Pbw38N/F2sz6fK2iXk2j2sQBliXqCTllz6YrC0vw9qWq3S2trbyXdyzMAscTM688FsV+mOjwx6foUdpa2y2aQx7I4gAdq9wfWtf4beB/DnhvUL24i0O3t5CBKt24Hftjr1B/OvBngJxnqfUYbP4wpe7HU8/8A2Zfhpqnwv+G32HVwRdX121+FPVVaONAMduYz1r5Yg12+brbEf8DFfoNe6mdVuXcwPAIz5a7xgMBzuA7Dn9K/NqO+cjcrKVHo1enOny04R7Hy06zxNadaW7Z1EXiG/Tj7IGPp5yr/ADNSp4m1t5BHBozTMeABdRj+ZrmU1XK8bfqeP51o6Nqrfb4uVJBzgtx+lcU01qy43vodZeah4l03ylvdKMCsu4D7TG38jWXJr+qSKdthKD71p+NvFPnyWpeVQfL2gIM1x9xrjqpJII/3m/xqY1EzWo58u5PeeJdegTI09WGf4n2/zNNXxLqAjDvZHd6LKprPGrfaI22vgDqAc/zqpJqbbCQ5P1wK0VRXONNtanqP7Pvie8vvjLoFtLYPDG/2jMhbIGLeU/0r7Rr4c/Zx1Dz/AI1+HE3jDfaeM/**********/V/iT4MksdL0Q3N4kgeKM3Spnr3ZwPzr0iirrUY1o8sjTDV3hpupFJt97/o0fAMv7NHxRa6Rv+EQYoOp/tG0/+O1u+Dfgd8VPCfjCyvo/CEpsmOLnGp2gGOMcebz3r7horihl1KDum/w/yPoqnEeKq01TcI2Sts//AJI898LW3iCxBS80CRY+oBu4z/J66S7m1CV42XRS23qDcj/4ut6ivaVWSjyHyMoKUnLucuj6jExP9h3Dk9/Ph4/8erCePxPeeKYprrRbptLjVMBLyFckMSRgP9K9ForGp+9d2awbpqyJrq7jvHWSO2e1G0AxuwY5+oJr4Ag/Zn+Kfyh/DXljvt1C2/8AjtffNFYypqaSbKjNxvY+A3/Zq+KwLRjwwzxZzn+0bX/47VnTv2bvijY3Ecn/AAjDFc8r/aFr0/7+1950Vg8LB7tmntpHw/rP7PvxOuyUh8NllI+8b+2+X/yJWM/7N/xY8javhgk/9hC1/wDjtffNFQsFTXVjlXnJWZ8At+zT8V4U3ReGCzkcr/aFqP8A2rUE/wCzV8XHiVh4Uy4/g/tG0/8AjtfoLRVfVKfmZqo0fHHwA+BnxE8HfFnw9q+veGxYaXbfaPPuPttvJs3W8ir8qSFjlmUcDvX2PRRXTTpqmrIiUnJ3Z//Z
                      chatroomId: '**********@chatroom'
                '2':
                  summary: 异常示例
                  value:
                    ret: 500
                    msg: 创建群聊失败
                    data:
                      code: '0'
                      msg: MemberList are wrong
          headers: {}
          x-apifox-name: 成功
      security: []
      x-apifox-folder: 核心 API 模块/群管理接口
      x-apifox-status: released
      x-run-in-apifox: https://app.apifox.com/web/project/4425884/apis/api-170454710-run
components:
  schemas: {}
  securitySchemes: {}
servers:
  - url: http://api.wechatapi.net/finder/v2/api
    description: 测试环境
security: []

```
