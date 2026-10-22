import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { fileUrl } from "@/api/client";
import { AudioPlayer } from "@/components/AudioPlayer";
import { renderAt } from "@/test/render";

const LABEL_A = "候选 A";
const LABEL_B = "候选 B";

describe("AudioPlayer", () => {
  const played: string[] = [];

  beforeEach(() => {
    // jsdom does not play media: fire the events a browser would.
    vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(function (
      this: HTMLMediaElement,
    ) {
      played.push(this.src);
      this.dispatchEvent(new Event("play"));
      return Promise.resolve();
    });
    vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(function (
      this: HTMLMediaElement,
    ) {
      this.dispatchEvent(new Event("pause"));
    });
  });

  afterEach(() => {
    played.length = 0;
    vi.restoreAllMocks();
  });

  it("plays one clip at a time and shows its waveform and duration", async () => {
    const user = userEvent.setup();
    renderAt(
      <div>
        <AudioPlayer
          src={fileUrl("a".repeat(64))}
          waveform={[0.2, 0.8]}
          duration={1.84}
          label={LABEL_A}
        />
        <AudioPlayer src={fileUrl("b".repeat(64))} duration={2} label={LABEL_B} />
      </div>,
      "/",
    );
    expect(screen.getByText("1.8 秒")).toBeInTheDocument();
    const a = screen.getByRole("button", { name: "播放：候选 A" });
    await user.click(a);
    expect(screen.getByRole("button", { name: "暂停：候选 A" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(played[0]).toContain(`/api/v1/files/${"a".repeat(64)}`);

    await user.click(screen.getByRole("button", { name: "播放：候选 B" }));
    // Starting B paused A.
    expect(screen.getByRole("button", { name: "播放：候选 A" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    await user.click(screen.getByRole("button", { name: "暂停：候选 B" }));
    expect(screen.getByRole("button", { name: "播放：候选 B" })).toBeInTheDocument();
  });
});
