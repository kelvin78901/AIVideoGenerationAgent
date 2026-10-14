import { compare, flatten } from "./check-i18n";

describe("check-i18n", () => {
  it("flattens nested keys", () => {
    expect([...flatten({ a: { b: "x", c: { d: "y" } } }).keys()]).toEqual(["a.b", "a.c.d"]);
  });

  it("passes when both locales match", () => {
    expect(compare({ "zh-CN": { common: { a: "甲" } }, en: { common: { a: "A" } } })).toEqual([]);
  });

  it("reports missing, extra and empty keys and missing files", () => {
    const problems = compare({
      "zh-CN": { common: { a: "甲", b: "乙" }, nav: { x: "x" } },
      en: { common: { a: "A", c: "C", d: " " } },
    });
    expect(problems).toEqual(
      expect.arrayContaining([
        'en/common: missing "b"',
        'zh-CN/common: missing "c"',
        'en/common: "d" is empty',
        "en/nav.json is missing",
      ]),
    );
  });
});
