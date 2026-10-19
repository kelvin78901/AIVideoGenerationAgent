import { act, renderHook } from "@testing-library/react";

import type { ItemInstall, MachineProfile, SetupItem } from "@/api/schemas/setup";
import "@/i18n";
import { estimate, overallPct, timeLeft, useUnits } from "@/pages/setup/items";
import { useUiStore } from "@/stores/ui";
import { fakeSetup, installState, itemOf, resetFakeSetup } from "@/test/setupBackend";

/** The PC sample machine after its scan (22 MB/s measured), installing `ids`. */
function installing(ids: string[], installs: Record<string, Partial<ItemInstall>>): MachineProfile {
  resetFakeSetup("pc", { scanned: true });
  const p = structuredClone(fakeSetup.profile);
  p.phase = "installing";
  p.install = {
    items: ids,
    mirror: "auto",
    dir: "D:\\DramaStudio",
    confirm: [],
    changes: [],
    snapshot: null,
    snapshot_error: null,
  };
  for (const x of p.items)
    x.install = ids.includes(x.id) ? { ...installState("queued"), ...installs[x.id] } : null;
  return p;
}

const pick = (p: MachineProfile, ...ids: string[]): SetupItem[] =>
  p.items.filter((x) => ids.includes(x.id));

describe("estimates", () => {
  it("downloads at the measured speed, the rest by rule of thumb", () => {
    const p = installing([], {});
    // FFmpeg 60 s; IndexTTS 5.5 GB at 22 MB/s = 250 s.
    expect(estimate(pick(p, "ffmpeg", "w_tts"), 22e6)).toEqual({ bytes: 5.5e9, seconds: 310 });
    expect(estimate(pick(p, "ffmpeg", "w_tts"), null)).toEqual({ bytes: 5.5e9, seconds: null });
    expect(estimate(pick(p, "ffmpeg", "comfy"), null)).toEqual({ bytes: 0, seconds: 140 });
  });

  it("time left: the running download at its own speed, the queued ones too", () => {
    const p = installing(["ffmpeg", "w_sr", "w_tts"], {
      ffmpeg: { state: "done", pct: 100 },
      w_sr: {
        state: "running",
        pct: 50,
        bytes_done: 4.4e9,
        bytes_total: 8.8e9,
        speed: 44e6,
        eta_s: 100,
      },
    });
    // SeedVR2 100 s left; IndexTTS 5.5 GB at the live 44 MB/s = 125 s.
    expect(timeLeft(p)).toBe(225);
    const sr = itemOf(p, "w_sr");
    sr.install = { ...installState("running", 50), bytes_done: 4.4e9, bytes_total: 8.8e9 }; // between files
    expect(timeLeft(p)).toBe(200 + 250); // at the measured 22 MB/s
    p.download_bps = null;
    expect(timeLeft(p)).toBeNull();
    expect(timeLeft({ ...p, phase: "done" })).toBeNull();
  });

  it("the overall bar weighs each item by its rough time", () => {
    // FFmpeg (60 s) done, IndexTTS (250 s) not started: 60 / 310.
    const p = installing(["ffmpeg", "w_tts"], { ffmpeg: { state: "done", pct: 100 } });
    expect(overallPct(p)).toBe(19);
    // Half of IndexTTS too: (60 + 125) / 310. By item count it would be 75 %.
    itemOf(p, "w_tts").install = installState("running", 50);
    expect(overallPct(p)).toBe(60);
  });
});

describe("useUnits", () => {
  afterEach(() => act(() => useUiStore.setState({ lang: "zh-CN" })));

  it("writes sizes, speeds and durations in both languages", () => {
    const { result } = renderHook(() => useUnits());
    const u = result.current;
    expect([u.size(49.3e9), u.size(612e6), u.speed(18.62e6)]).toEqual([
      "49.3 GB",
      "612 MB",
      "18.6 MB/s",
    ]);
    expect([u.duration(30), u.duration(310), u.duration(5414), u.duration(7200)]).toEqual([
      "不到 1 分钟",
      "6 分钟",
      "1 小时 31 分钟",
      "2 小时",
    ]);
    expect(u.estimateText({ bytes: 5.5e9, seconds: 310 })).toBe("约 5.5 GB，预计 6 分钟");
    expect(u.estimateText({ bytes: 5.5e9, seconds: null })).toBe(
      "约 5.5 GB（还没测过下载速度，算不出用时）",
    );
    expect(u.estimateText({ bytes: 0, seconds: 140 })).toBe("预计 3 分钟");

    act(() => useUiStore.setState({ lang: "en" }));
    const { result: en } = renderHook(() => useUnits());
    expect(en.current.duration(5414)).toBe("1 h 31 min");
    expect(en.current.estimateText({ bytes: 5.5e9, seconds: 310 })).toBe(
      "About 5.5 GB, roughly 6 min",
    );
  });
});
