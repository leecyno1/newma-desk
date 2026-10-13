import '@testing-library/jest-dom/vitest';
import { useState } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { SnapshotHoldingEditor } from './SnapshotHoldingEditor';
import type { Holding } from './PortfolioDiagnosis';

afterEach(cleanup);
const original:Holding={assetType:'fund',market:'CN',symbol:'000001',name:'合成基金',account:'A',currency:'CNY',bookValue:100,
  fxToBase:1,availableCash:null,equityBeta:0.5,equityBenchmark:'沪深300',ratePnlPerBp:-1,direction:null,notional:null,
  source:'合成依据',proceedsAmount:50,proceedsDate:'2026-10-01',proceedsAccount:'A',proceedsSource:'合成计划'};
function Harness(){const [rows,setRows]=useState([original]);return <><SnapshotHoldingEditor holdings={rows} onChange={setRows}/><output data-testid="rows">{JSON.stringify(rows)}</output></>}
const rows=()=>JSON.parse(screen.getByTestId('rows').textContent!);

it('adds an unknown row without copying valuation, sensitivities or receipts',()=>{
  render(<Harness/>);
  expect(screen.getByRole('button',{name:'移除当前行'})).toBeDisabled();
  fireEvent.click(screen.getByRole('button',{name:'新增持仓行'}));
  expect(rows()[0]).toEqual(original);
  expect(rows()[1]).toMatchObject({assetType:'other',symbol:'',account:'A',currency:'CNY',bookValue:null,fxToBase:null,equityBeta:null,ratePnlPerBp:null});
  expect(rows()[1].proceedsAmount).toBeUndefined();
  expect(screen.getByLabelText('选择持仓')).toHaveValue('1');
});

it('confirms removal, selects a remaining row and restores the exact removed input',()=>{
  render(<Harness/>);
  fireEvent.click(screen.getByRole('button',{name:'新增持仓行'}));
  fireEvent.change(screen.getByLabelText('选择持仓'),{target:{value:'0'}});
  fireEvent.click(screen.getByRole('button',{name:'移除当前行'}));
  fireEvent.click(screen.getByRole('button',{name:'保留此行'}));
  expect(rows()).toHaveLength(2);
  fireEvent.click(screen.getByRole('button',{name:'移除当前行'}));
  fireEvent.click(screen.getByRole('button',{name:'确认移除此行'}));
  expect(rows()).toHaveLength(1);
  expect(screen.getByLabelText('选择持仓')).toHaveValue('0');
  fireEvent.click(screen.getByRole('button',{name:'撤销上次移除'}));
  expect(rows()[0]).toEqual(original);
  expect(rows()).toHaveLength(2);
  expect(screen.getByRole('button',{name:'移除当前行'})).toBeEnabled();
});
