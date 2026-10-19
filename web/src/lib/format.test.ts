import { formatBytes, formatDateTime } from "./format";

describe("formatBytes", () => {
  it.each([
    [0, "0 B"],
    [900, "900 B"],
    [2048, "2 KB"],
    [228456789, "218 MB"],
    [335304388, "320 MB"],
    [6938078334, "6.5 GB"],
    [1.5 * 1024 ** 4, "1.5 TB"],
  ])("%d → %s", (bytes, text) => {
    expect(formatBytes(bytes)).toBe(text);
  });
});

describe("formatDateTime", () => {
  it("shows the local day and time", () => {
    const d = new Date(2026, 9, 18, 9, 5);
    expect(formatDateTime(d.toISOString())).toBe("2026-10-18 09:05");
  });
});
