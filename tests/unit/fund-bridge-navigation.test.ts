// @vitest-environment jsdom
import {afterEach,expect,it,vi} from 'vitest';
import {createNewmaDeskBridge} from '../../bundled-runtimes/fund-analysis/lib/newma-desk/bridge';

afterEach(()=>{vi.restoreAllMocks();vi.useRealTimers();});

it('defers navigation until a trusted init, keeps latest intent and clears it on close',()=>{
  vi.useFakeTimers();
  const parent={postMessage:vi.fn()};
  vi.spyOn(window,'self','get').mockReturnValue({} as Window);
  vi.spyOn(window,'parent','get').mockReturnValue(parent as unknown as Window);
  const bridge=createNewmaDeskBridge({modId:'fund-research-library',parentOrigin:'http://localhost:5888',
    initialContext:{view:{id:'research',title:'基金'},visibleBlocks:[],selection:{},filters:{},data:{},actions:[],tasks:[]}});
  expect(bridge.navigate('fund-research-library','view=managers&managerId=old')).toBe(true);
  expect(bridge.navigate('fund-research-library','view=managers')).toBe(true);
  const init={type:'vibedesk:init',protocolVersion:'1.0',modId:'fund-research-library',instanceId:'test',
    user:{id:'test'},workspace:{id:'test'},environment:{theme:'dark',locale:'zh-CN',timezone:'Asia/Shanghai'},
    gateways:{actions:'http://localhost/actions',agent:'http://localhost/agent',model:'http://localhost/model',data:'http://localhost/data'},
    grants:{permissions:[],actions:[]}};
  const navigations=()=>parent.postMessage.mock.calls.filter(([m])=>m.type==='vibedesk:navigate');
  window.dispatchEvent(new MessageEvent('message',{source:parent as unknown as Window,origin:'https://wrong.test',data:init}));
  expect(navigations()).toHaveLength(0);
  window.dispatchEvent(new MessageEvent('message',{source:parent as unknown as Window,origin:'http://localhost:5888',data:init}));
  expect(navigations()).toHaveLength(1);
  expect(navigations()[0][0]).toMatchObject({search:'view=managers',instanceId:'test'});
  window.dispatchEvent(new MessageEvent('message',{source:parent as unknown as Window,origin:'http://localhost:5888',data:init}));
  expect(navigations()).toHaveLength(1);
  bridge.close();
  expect(bridge.navigate('fund-research-library','view=reports')).toBe(false);
  vi.clearAllTimers();
});
