import '@testing-library/jest-dom/vitest';
import { cleanup,render,screen } from '@testing-library/react';
import { afterEach,expect,it } from 'vitest';
import { NavThresholds } from './NavThresholds';

afterEach(cleanup);
it('keeps old reports explicit instead of fabricating a threshold assessment',()=>{
  render(<NavThresholds currency="CNY"/>);
  expect(screen.getByText(/此版本尚无分级预警结果/)).toBeVisible();
  expect(screen.queryByRole('table')).toBeNull();
});
it('renders equality and missing inputs with distinct risk labels',()=>{
  render(<NavThresholds currency="CNY" data={{warningLine:95,floor:80,rows:[{label:'快照',nav:95,warningHeadroom:0,floorHeadroom:15,status:'warning'},{label:'未知情景',nav:null,warningHeadroom:null,floorHeadroom:null,status:'unassessed'}]}}/>);
  expect(screen.getByRole('table')).toHaveTextContent('触发预警');
  expect(screen.getByRole('table')).toHaveTextContent('未评估');
  expect(screen.getByText(/这里只提示，不自动减仓/)).toBeVisible();
});
