import { cn } from "./utils";

describe("cn", () => {
  it("merges conflicting tailwind classes", () => {
    const hidden = false;
    expect(cn("px-2 text-sm", hidden && "hidden", "px-4")).toBe("text-sm px-4");
  });
});
