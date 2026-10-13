import {render, screen, within} from '@testing-library/react';
import {describe, expect, it} from 'vitest';
import {CopilotMarkdown} from './CopilotMarkdown';

describe('Copilot Markdown',()=>{
  it('renders financial tables, headings, citations and code without changing values',()=>{
    const {container}=render(<CopilotMarkdown content={'## 核心结论\n\n**现金流须拆分。**\n\n1. 检查合并范围\n2. 核对单位\n\n| 指标 | 金额 |\n| --- | ---: |\n| 营业收入 | 1,708.99亿元 |\n\n> PDF物理第5页\n\n```text\nsource: revenue\n```'}/>);
    expect(screen.getByRole('heading',{name:'核心结论',level:2})).toBeVisible();
    expect(container.querySelector('strong')).toHaveTextContent('现金流须拆分。');
    expect(within(screen.getByRole('table')).getByRole('cell',{name:'1,708.99亿元'})).toBeVisible();
    expect(screen.getAllByRole('listitem')).toHaveLength(2);
    expect(container.querySelector('blockquote')).toHaveTextContent('PDF物理第5页');
    expect(container.querySelector('pre code')).toHaveTextContent('source: revenue');
  });

  it('does not execute HTML, expose unsafe links or load inline images',()=>{
    const {container}=render(<CopilotMarkdown content={'<script>alert(1)</script>\n\n<iframe src="https://example.com"></iframe>\n\n[原报](https://example.com/report.pdf#page=5) [坏链接](javascript:alert%281%29)\n\n![外部图片](https://example.com/tracker.png)'}/>);
    expect(container.querySelector('script,iframe,img')).toBeNull();
    expect(screen.queryByRole('link',{name:'坏链接'})).toBeNull();
    const link=screen.getByRole('link',{name:'原报'});
    expect(link).toHaveAttribute('href','https://example.com/report.pdf#page=5');
    expect(link).toHaveAttribute('rel','noopener noreferrer');
    expect(link).toHaveAttribute('target','_blank');
    expect(screen.getByText('[图片：外部图片]')).toBeVisible();
  });

  it('keeps same-numbered footnotes inside their own answer',()=>{
    const content='说明[^1]\n\n[^1]: 原文证据';
    const {container}=render(<><CopilotMarkdown content={content}/><CopilotMarkdown content={content}/></>);
    const citations=[...container.querySelectorAll<HTMLAnchorElement>('a[data-footnote-ref]')];
    expect(citations).toHaveLength(2);
    expect(citations[0]!.hash).not.toBe(citations[1]!.hash);
    for(const citation of citations){
      const target=document.getElementById(decodeURIComponent(citation.hash.slice(1)));
      expect(target).toHaveTextContent('原文证据');
      expect(citation).not.toHaveAttribute('target');
    }
  });
});
