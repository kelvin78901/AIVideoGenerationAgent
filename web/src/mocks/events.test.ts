import { repeatDemo } from "@/mocks/events";

afterEach(() => {
  vi.useRealTimers();
});

describe("repeatDemo", () => {
  it("with a delay, runs one step per tick until the step returns false", () => {
    vi.useFakeTimers();
    const seen: number[] = [];
    let n = 0;
    repeatDemo(100, () => {
      seen.push((n += 1));
      return n < 3;
    });
    expect(seen).toEqual([]);
    vi.advanceTimersByTime(100);
    expect(seen).toEqual([1]);
    vi.advanceTimersByTime(1000);
    expect(seen).toEqual([1, 2, 3]);
  });

  it("with zero delay, runs every step in one task", () => {
    vi.useFakeTimers();
    let n = 0;
    repeatDemo(0, () => (n += 1) < 120);
    expect(n).toBe(0); // never synchronous: the HTTP response goes out first
    vi.advanceTimersToNextTimer();
    expect(n).toBe(120);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("stops when alive() turns false (a newer run or a db reset)", () => {
    vi.useFakeTimers();
    let alive = true;
    let n = 0;
    repeatDemo(
      10,
      () => {
        n += 1;
        return true;
      },
      () => alive,
    );
    vi.advanceTimersByTime(30);
    alive = false;
    vi.advanceTimersByTime(100);
    expect(n).toBe(3);
    expect(vi.getTimerCount()).toBe(0);

    let m = 0;
    repeatDemo(
      0,
      () => (m += 1) < 1_000_000,
      () => m < 5,
    );
    vi.advanceTimersToNextTimer();
    expect(m).toBe(5);
  });
});
