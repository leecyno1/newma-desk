/* Shared evidence rules for the dashboard; these are candidate signals, not AI conclusions. */
(function (root) {
    const formats = /^(?:pdf|docx?|xlsx?|excel|pptx?|csv|txt|md|zip|rar|7z|jpg|jpeg|png|gif|webp|mp[34]|m4a|wav|ogg|xml|json|附件|庆祝|玫瑰|红包|太阳|抱拳|感兴趣|不知道|不清楚|没关系|没问题|有时间|感受一下|核心观点|范围交流|第[一二三四五六七八九十\d]+次)$/i;
    const emoji = /\[(?:庆祝|玫瑰|红包|太阳|抱拳|礼物|强|微笑|握手|烟花|旺柴|嘿哈)\]/g;
    function clean(text) {
        return String(text || '').replace(emoji, ' ').replace(/<[^>]*>/g, ' ')
            .replace(/^\s*\d{8,14}\s*(?:电话|腾讯)?\s*\|\s*/, '')
            .replace(/https?:\/\/\S+/gi, ' ').replace(/\.(?:pdf|docx?|xlsx?|pptx?|csv|zip|rar)\b/gi, ' ')
            .replace(/\s+/g, ' ').trim();
    }
    function opportunity(text) {
        const value = clean(text);
        // An invitation, a positive emoji or a task is not an investment thesis.
        const sentences = value.split(/[。；;\n]/).filter(s => s.trim().length >= 12);
        return sentences.some(s =>
            !/(?:会议主题|议题|交流主题|路演主题|欢迎.*(?:参会|报名)|诚邀|报名链接|时间[:：]|地点[:：])/.test(s)
            && /看好|受益|上调|超预期|拐点|提价|加仓|增长|增速|改善|突破|催化|推荐|买入/.test(s)
            && /订单|利润|营收|收入|业绩|估值|产能|需求|份额|现金流|政策|成本|销量|价格|盈利|回购/.test(s)
            && !/不推荐|不看好|未超预期|并非利好/.test(s)
        );
    }
    const research = /财报|营收|净利润|盈利预测|估值|上市公司|产业链|行业研究|行业报告|投资逻辑|业绩|并购|重组|回购|分红|融资|招股|IPO|票房.{0,12}(增长|同比|收入)|市场规模/i;
    const gossip = /生日|庆生|生快|恋情|绯闻|官宣恋爱|出轨|分手|复合|塌房|嗑CP|磕CP|粉丝应援|机场穿搭|红毯造型|路透照|生图|颜值|追星|饭圈|吃瓜|八卦/i;
    function contentNoise(item) {
        const title=String(item?.title||''), text=['title','summary','description','desc','content'].map(k=>String(item?.[k]||'')).join(' ');
        if (research.test(title)) return false;
        if (gossip.test(title)) return true;
        if (/扫码.{0,10}(领取|进群|购买)|加微信|购买链接|限时.{0,8}(优惠|秒杀)|抽奖|免费送|招商加盟|课程报名|训练营/.test(title)) return true;
        return (gossip.test(text) || /明星|综艺|电视剧|穿搭|美妆|护肤|减肥|瘦身|育儿|星座|情感|宠物|探店|菜谱|婚礼|婚恋|娱乐|演唱会/.test(text)) && !research.test(text);
    }
    root.DeepseeIntelligence = { clean, opportunity, contentNoise, researchTitle: item=>research.test(String(item?.title||'')), isNoise: word => formats.test(String(word || '').trim()) };
    if (typeof module !== 'undefined') module.exports = root.DeepseeIntelligence;
})(typeof window !== 'undefined' ? window : globalThis);
