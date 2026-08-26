import { Fragment, type ReactNode } from "react";

const INLINE = /(`[^`\n]+`|\*\*[^*\n]+\*\*|~~[^~\n]+~~|\*[^*\n]+\*|\[[^\]\n]+\]\([^\s)]+\))/g;
const LIST = /^\s*(?:([-*+])|(\d+)\.)\s+(.+)$/;
const HEADING = /^(#{1,4})\s+(.+)$/;
const TABLE_RULE = /^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$/;

function safeHref(value: string) {
  return /^(https?:\/\/|mailto:|#)/i.test(value) ? value : null;
}

function inline(value: string, key: string): ReactNode[] {
  return value.split(INLINE).filter(Boolean).map((token, index) => {
    const itemKey = `${key}:${index}`;
    if (token.startsWith("`") && token.endsWith("`")) return <code key={itemKey} className="rounded bg-muted px-1.5 py-0.5 font-mono text-[.92em]">{token.slice(1, -1)}</code>;
    if (token.startsWith("**") && token.endsWith("**")) return <strong key={itemKey} className="font-semibold text-foreground">{token.slice(2, -2)}</strong>;
    if (token.startsWith("~~") && token.endsWith("~~")) return <del key={itemKey}>{token.slice(2, -2)}</del>;
    if (token.startsWith("*") && token.endsWith("*")) return <em key={itemKey}>{token.slice(1, -1)}</em>;
    const link = /^\[([^\]]+)\]\(([^\s)]+)\)$/.exec(token);
    if (link) {
      const href = safeHref(link[2]!);
      return href ? <a key={itemKey} href={href} target={href.startsWith("#") ? undefined : "_blank"} rel="noreferrer" className="font-medium text-primary underline decoration-primary/35 underline-offset-2 hover:decoration-primary">{link[1]}</a> : token;
    }
    return <Fragment key={itemKey}>{token}</Fragment>;
  });
}

function cells(line: string) {
  return line.trim().replace(/^\||\|$/g, "").split("|").map((cell) => cell.trim());
}

function startsBlock(lines: string[], index: number) {
  const line = lines[index] || "";
  return !line.trim() || line.startsWith("```") || HEADING.test(line) || LIST.test(line) || /^>\s?/.test(line) || /^\s*(?:---+|___+|\*\*\*+)\s*$/.test(line) || (line.includes("|") && TABLE_RULE.test(lines[index + 1] || ""));
}

export function ResearchText({ content, className = "" }: { content: string; className?: string }) {
  const lines = content.replace(/\r\n?/g, "\n").slice(0, 120_000).split("\n");
  const blocks: ReactNode[] = [];
  for (let index = 0; index < lines.length;) {
    const line = lines[index] || "";
    if (!line.trim()) { index += 1; continue; }
    if (line.startsWith("```")) {
      const language = line.slice(3).trim();
      const body: string[] = [];
      index += 1;
      while (index < lines.length && !lines[index]!.startsWith("```")) body.push(lines[index++]!);
      if (index < lines.length) index += 1;
      blocks.push(<pre key={`code:${index}`} className="overflow-x-auto rounded-xl border border-border bg-card/80 p-4 text-xs leading-6"><code data-language={language || undefined}>{body.join("\n")}</code></pre>);
      continue;
    }
    const heading = HEADING.exec(line);
    if (heading) {
      const level = heading[1]!.length;
      const Tag = `h${level}` as "h1" | "h2" | "h3" | "h4";
      blocks.push(<Tag key={`heading:${index}`} className={level === 1 ? "pt-1 text-xl font-bold" : level === 2 ? "pt-1 text-lg font-bold" : "pt-1 text-base font-semibold"}>{inline(heading[2]!, `heading:${index}`)}</Tag>);
      index += 1;
      continue;
    }
    if (line.includes("|") && TABLE_RULE.test(lines[index + 1] || "")) {
      const header = cells(line);
      index += 2;
      const body: string[][] = [];
      while (index < lines.length && lines[index]!.includes("|") && lines[index]!.trim()) body.push(cells(lines[index++]!));
      blocks.push(<div key={`table:${index}`} className="overflow-x-auto rounded-xl border border-border"><table className="w-full border-collapse text-left text-xs"><thead className="bg-muted/35"><tr>{header.map((cell, column) => <th key={column} className="border-b border-border px-3 py-2 font-semibold">{inline(cell, `th:${index}:${column}`)}</th>)}</tr></thead><tbody>{body.map((row, rowIndex) => <tr key={rowIndex} className="even:bg-muted/15">{header.map((_, column) => <td key={column} className="border-b border-border/60 px-3 py-2 align-top last:border-b-0">{inline(row[column] || "", `td:${index}:${rowIndex}:${column}`)}</td>)}</tr>)}</tbody></table></div>);
      continue;
    }
    const list = LIST.exec(line);
    if (list) {
      const ordered = Boolean(list[2]);
      const items: string[] = [];
      while (index < lines.length) {
        const match = LIST.exec(lines[index] || "");
        if (!match || Boolean(match[2]) !== ordered) break;
        items.push(match[3]!); index += 1;
      }
      const Tag = ordered ? "ol" : "ul";
      blocks.push(<Tag key={`list:${index}`} className={`${ordered ? "list-decimal" : "list-disc"} space-y-1 pl-5`}>{items.map((item, itemIndex) => <li key={itemIndex}>{inline(item, `li:${index}:${itemIndex}`)}</li>)}</Tag>);
      continue;
    }
    if (/^>\s?/.test(line)) {
      const quote: string[] = [];
      while (index < lines.length && /^>\s?/.test(lines[index] || "")) quote.push((lines[index++] || "").replace(/^>\s?/, ""));
      blocks.push(<blockquote key={`quote:${index}`} className="border-l-2 border-primary/55 pl-4 text-muted-foreground">{inline(quote.join(" "), `quote:${index}`)}</blockquote>);
      continue;
    }
    if (/^\s*(?:---+|___+|\*\*\*+)\s*$/.test(line)) { blocks.push(<hr key={`hr:${index}`} className="border-border" />); index += 1; continue; }
    const paragraph: string[] = [];
    while (index < lines.length && !startsBlock(lines, index)) paragraph.push(lines[index++]!.trim());
    blocks.push(<p key={`p:${index}`} className="whitespace-pre-wrap">{inline(paragraph.join(" "), `p:${index}`)}</p>);
  }
  return <div className={`space-y-3 text-sm leading-7 text-foreground/90 ${className}`}>{blocks}</div>;
}
