import { GLOBAL_TOPICS, type GlobalTopicId } from "./topicContext";

export const GLOBAL_PAGES: Array<{ id: string; title: string; topicId?: GlobalTopicId }> = [
  { id: "global-situation", title: "全球情报" },
  ...(Object.keys(GLOBAL_TOPICS) as GlobalTopicId[]).map(topicId => ({ ...GLOBAL_TOPICS[topicId], topicId })),
];

export function topicFromSearch(search: string): GlobalTopicId | undefined {
  const params = new URLSearchParams(search);
  const topic = params.get("topic");
  if (topic && Object.hasOwn(GLOBAL_TOPICS, topic)) return topic as GlobalTopicId;
  return GLOBAL_PAGES.find(page => page.id === params.get("mod"))?.topicId;
}

export function globalPageHref(href: string, page: typeof GLOBAL_PAGES[number]) {
  const url = new URL(href);
  url.searchParams.set("mod", page.id);
  if (page.topicId) url.searchParams.set("topic", page.topicId);
  else url.searchParams.delete("topic");
  return url.pathname + url.search + url.hash;
}
