import { describe, expect, it } from "vitest";

import { serializeEmbeddedJson } from "./embeddedJson";

describe("serializeEmbeddedJson", () => {
  it("round-trips JSON while escaping HTML-significant characters", () => {
    const value = {
      text: "</script><script>alert('x') & continue</script>",
      separators: "line\u2028paragraph\u2029end",
    };

    const serialized = serializeEmbeddedJson(value);

    expect(serialized).not.toMatch(/[<>&\u2028\u2029]/u);
    expect(JSON.parse(serialized)).toEqual(value);
  });

  it("serializes chart-shaped values without changing their data", () => {
    const option = {
      xAxis: { data: ["周一", "周二"] },
      series: [{ type: "line", data: [1, 2] }],
    };

    expect(JSON.parse(serializeEmbeddedJson(option))).toEqual(option);
  });
});
