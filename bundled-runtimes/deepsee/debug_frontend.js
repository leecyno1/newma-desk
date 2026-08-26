// 测试前端渲染逻辑
const testMessage = {
    "id": 190,
    "content": null,
    "content_text": "能源开采【6】！！\n能源开采【6】！！\n能源开采【6】！！\n\n[红包]【国海能源开采】煤炭专题研究系列会议",
    "derived": {
        // 现已移除 key_info，统一使用 summary 和 summary_origin 两段式
        "summary": "ai: 国海能源开采举办电解铝行业投资机会专题会议，介绍煤炭专题研究系列会议回顾。",
        "summary_origin": "tool",
        "keywords": ["国海能源开采","专题会议"],
        "meeting_number": "065971",
        "platform": "进门"
    },
    "sender_name": "李畅@信达策略",
    "talker_name": "信达研究❤️南方基金投研干货群"
};

// 模拟前端逻辑
function testContentExtraction(m) {
    console.log("=== 测试消息内容提取 ===");
    console.log("m.content:", m.content);
    console.log("m.content_text:", m.content_text);
    
    // 这是前端代码中的逻辑
    let content = m.content || m.content_text || '';
    console.log("提取的content:", content);
    console.log("content长度:", content.length);
    console.log("content前100字符:", content.slice(0, 100));
    
    return content;
}

function testSummaryExtraction(meta) {
    console.log("\n=== 测试summary提取（两段式） ===");
    console.log("meta.derived:", meta.derived);
    const d = meta.derived || {};
    let summary = (d.summary || '').trim();
    let origin = (d.summary_origin || '').trim();
    // 展示层建议去掉前缀“ai:”/“fallback:”，但保留颜色区分
    const display = summary.replace(/^\s*(ai:|fallback:)\s*/i, '');
    const cssClass = origin === 'tool' ? 'ai' : 'fallback';
    console.log("原始summary:", summary);
    console.log("显示summary:", display);
    console.log("来源origin:", origin);
    console.log("建议样式类:", cssClass);
    return { display, origin, cssClass };
}

console.log("开始测试...");
const content = testContentExtraction(testMessage);
const { display, origin, cssClass } = testSummaryExtraction(testMessage);

console.log("\n=== 最终结果 ===");
console.log("内容是否为空:", content === '');
console.log("display是否为空:", display === '');
console.log("origin:", origin, "cssClass:", cssClass);



