import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_protocol_payloads_are_not_readable_summaries():
    source = (ROOT / 'static/index.html').read_text()
    helpers = source.split('        function isWechatProtocolText', 1)[1].split('        function mapBackendMessage', 1)[0]
    js = 'function isWechatProtocolText' + helpers + '''
console.log(JSON.stringify([
  formatMessageSummary('<?xml version="1.0"?><msg><img aeskey="secret"/></msg>', 'image'),
  formatMessageSummary('020100044 | <img aeskey="secret"', 'image'),
  formatMessageSummary('公司收入增长 10%', 'image'),
  formatMessageSummary('<msg><voicemsg/></msg>', 'voice'),
  formatMessageSummary('<msg><img aeskey="secret"/></msg>', '图片'),
  formatMessageSummary('<msg><videomsg/></msg>', '')
]));
'''
    result = subprocess.run(['node', '-e', js], text=True, capture_output=True, check=True)
    assert json.loads(result.stdout) == ['[图片]', '[图片]', '公司收入增长 10%', '[语音]', '[图片]', '[视频]']


def test_dashboard_loads_samples_on_direct_entry():
    source = (ROOT / 'static/index.html').read_text()
    block = source.split("else if (targetModule === 'dashboard')", 1)[1].split('}catch', 1)[0]
    assert block.index('await ensureMessageListLoaded(force)') < block.index('renderDashboard')
    assert 'dashboardSampleStatus' in source


def test_protocol_messages_do_not_inherit_false_meeting_or_sentiment():
    source = (ROOT / 'static/index.html').read_text()
    functions = source.split('        function isWechatProtocolText', 1)[1].split('        function extractMessageText', 1)[0]
    js = '''
const normalizeWechatGatewayMedia = () => ({type: 'image'});
const normalizeToneValue = value => value;
const mapMsgTypeCode = () => '图片';
''' + 'function isWechatProtocolText' + functions + '''
const message = mapBackendMessage({
  content: '<msg><img aeskey="123456789"/></msg>',
  derived: {summary: '<img aeskey="123456789"/>', category: '提问', tone: 'negative', meeting_number: '123456789'}
});
console.log(JSON.stringify([message.summary, message.category, message.tone, message.meeting_number]));
'''
    result = subprocess.run(['node', '-e', js], text=True, capture_output=True, check=True)
    assert json.loads(result.stdout) == ['[图片]', '其他', 'neutral', '']


def test_message_types_match_filter_labels_for_both_protocols():
    source = (ROOT / 'static/index.html').read_text()
    mapping = source.split('        function mapMsgTypeCode', 1)[1].split('        function normalizeToneValue', 1)[0]
    js = 'function mapMsgTypeCode' + mapping + '''
console.log(JSON.stringify(['image', 3, '图片', 'text', 1, 'voice', 34, 'video', 43, 'link', 49].map(mapMsgTypeCode)));
'''
    result = subprocess.run(['node', '-e', js], text=True, capture_output=True, check=True)
    assert json.loads(result.stdout) == ['图片', '图片', '图片', '文字', '文字', '语音', '语音', '视频', '视频', '链接', '链接']


def test_confirmation_requires_explicit_acceptance_without_native_modals():
    source = (ROOT / 'static/index.html').read_text()
    helper = source.split('        function confirmAction', 1)[1].split('// Debug:', 1)[0]
    js = '''
let current;
const document = {
  body: {appendChild: dialog => {current = dialog;}},
  createElement: () => ({
    returnValue: '', setAttribute(){}, querySelector(){return {};},
    addEventListener(event, fn){this[event] = fn;}, showModal(){}, remove(){}
  })
};
''' + 'function confirmAction' + helper + '''
(async () => {
  const accepted = confirmAction('确认测试');
  current.returnValue = 'confirm'; current.close();
  const cancelled = confirmAction('取消测试');
  current.close();
  console.log(JSON.stringify([await accepted, await cancelled]));
})();
'''
    result = subprocess.run(['node', '-e', js], text=True, capture_output=True, check=True)
    assert json.loads(result.stdout) == [True, False]
    assert 'if (!confirm(' not in source
