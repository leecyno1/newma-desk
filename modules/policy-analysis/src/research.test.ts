import { expect, it } from "vitest";
import { sourceCoverage, withinPolicyWindow } from "./research";
import type { PolicyEvent, PolicySource } from "./types";

it("date windows exclude future and old publications, while all-history retains them", () => {
  expect(withinPolicyWindow({ date: "2026-10-01" } as PolicyEvent, "2026-10-14", 30)).toBe(true);
  expect(withinPolicyWindow({ date: "2026-08-01" } as PolicyEvent, "2026-10-14", 30)).toBe(false);
  expect(withinPolicyWindow({ date: "2026-10-15" } as PolicyEvent, "2026-10-14", 30)).toBe(false);
  expect(withinPolicyWindow({ date: "2020-01-01" } as PolicyEvent, "2026-10-14", 0)).toBe(true);
});

it("source coverage counts saved bodies, not merely discovered titles", () => {
  const source = { url: "https://www.gov.cn/" } as PolicySource;
  const events = [
    { status: "published", sourceUrl: "https://www.gov.cn/a", documentEvidence: { status: "available" } },
    { status: "published", sourceUrl: "https://www.gov.cn/b", documentEvidence: null },
    { status: "published", sourceUrl: "https://gov.cn.fake.example/c", documentEvidence: { status: "available" } },
    { status: "scheduled", sourceUrl: "https://www.gov.cn/window", documentEvidence: null },
  ] as PolicyEvent[];
  expect(sourceCoverage(source, events)).toEqual({ discovered: 2, readable: 1 });
});
