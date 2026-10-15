import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";

import { getDb } from "@/mocks/db";
import NovelPage from "@/pages/Novel";
import { backend } from "@/test/backend";
import { FakeEventSource } from "@/test/fakeEventSource";
import { renderAt } from "@/test/render";

// The user's own words, typed into the page (content, not UI copy).
const INSTRUCTION = "别写风衣，她今天穿的是工装外套";

function renderNovel() {
  return renderAt(
    <Routes>
      <Route path="/s/:series/e/:ep/novel" element={<NovelPage />} />
      <Route path="/s/:series/e/:ep/script" element={<div data-testid="script-page" />} />
    </Routes>,
    "/s/demo/e/1/novel",
  );
}

const card = (para: number, nth = 0) =>
  screen.getAllByRole("article", { name: `第 ${para} 段` })[nth] as HTMLElement;
const suggestion = (id: string) => getDb().suggestions.find((s) => s.id === id);

beforeEach(() => {
  vi.stubGlobal("EventSource", FakeEventSource);
  backend();
});
afterEach(() => vi.unstubAllGlobals());

describe("NovelPage", () => {
  it("shows the text with the adopted addition, counts and the bible", async () => {
    renderNovel();
    expect(await screen.findByText("177 字 · 5 段")).toBeInTheDocument();
    expect(screen.getByText("已采纳 1 / 4")).toBeInTheDocument();
    const added = screen.getByText(/她的米色风衣湿了半边/, { selector: "mark" });
    expect(added).toHaveTextContent("＋");
    expect(screen.getByRole("list", { name: "人物" })).toHaveTextContent("林晚 · 26 岁 · 插画师");
    expect(
      within(screen.getByRole("list", { name: "道具" })).getAllByRole("listitem"),
    ).toHaveLength(4);
    expect(screen.getByText("当前产物 · 补全建议 · 4 条")).toBeInTheDocument();
  });

  it("switches between 原文 / 采纳后 / 对比", async () => {
    const user = userEvent.setup();
    renderNovel();
    await screen.findByText("177 字 · 5 段");
    await user.click(screen.getByRole("radio", { name: "原文" }));
    expect(screen.queryByText(/她的米色风衣湿了半边/, { selector: "li p *" })).toBeNull();
    expect(screen.queryByText("蓝底带「＋」的是已采纳的补写。")).toBeNull();
    await user.click(screen.getByRole("radio", { name: "采纳后" }));
    expect(screen.getByText(/她的米色风衣湿了半边/, { selector: "span" })).toBeInTheDocument();
    expect(document.querySelector("li mark")).toBeNull();
  });

  it("adopts and un-adopts a suggestion; the text and counts follow", async () => {
    const user = userEvent.setup();
    renderNovel();
    await screen.findByText("177 字 · 5 段");
    const lighting = card(1, 1);
    await user.click(within(lighting).getByRole("button", { name: "采纳" }));
    expect(await screen.findByText("已采纳 2 / 4")).toBeInTheDocument();
    expect(screen.getByText("199 字 · 5 段")).toBeInTheDocument();
    expect(screen.getByText(/声控灯坏了一半/, { selector: "mark" })).toBeInTheDocument();
    await user.click(within(lighting).getByRole("button", { name: "撤销采纳" }));
    expect(await screen.findByText("已采纳 1 / 4")).toBeInTheDocument();
    expect(suggestion("s2")?.status).toBe("pending");
  });

  it("ignores and restores a suggestion", async () => {
    const user = userEvent.setup();
    renderNovel();
    await screen.findByText("177 字 · 5 段");
    await user.click(within(card(2)).getByRole("button", { name: "忽略" }));
    expect(await within(card(2)).findByText("已忽略")).toBeInTheDocument();
    await user.click(within(card(2)).getByRole("button", { name: "恢复" }));
    expect(await within(card(2)).findByText("待定")).toBeInTheDocument();
  });

  it("rewrites a suggestion on request", async () => {
    const user = userEvent.setup();
    renderNovel();
    await screen.findByText("177 字 · 5 段");
    const first = card(1, 0);
    await user.click(within(first).getByRole("button", { name: "改写要求" }));
    const submit = within(first).getByRole("button", { name: "按要求重写这一条" });
    expect(submit).toBeDisabled();
    await user.type(within(first).getByLabelText("告诉 AI 这一条怎么改"), INSTRUCTION);
    await user.click(submit);
    expect(await within(first).findByText("已按要求重写")).toBeInTheDocument();
    expect(within(first).getByText(/工装外套/, { selector: "blockquote" })).toBeInTheDocument();
    // Still adopted, so the text on the left now shows the rewritten addition.
    expect(screen.getByText(/工装外套/, { selector: "mark" })).toBeInTheDocument();
    expect(suggestion("s1")).toMatchObject({
      rewrite_instruction: INSTRUCTION,
      rewritten_by: "deepseek/v4-pro",
    });
  });

  it("「全部采纳」 adopts everything not ignored", async () => {
    const user = userEvent.setup();
    renderNovel();
    await screen.findByText("177 字 · 5 段");
    await user.click(within(card(4)).getByRole("button", { name: "忽略" }));
    await within(card(4)).findByText("已忽略");
    await user.click(screen.getByRole("button", { name: "全部采纳" }));
    expect(await screen.findByText("已采纳 3 / 4")).toBeInTheDocument();
    expect(suggestion("s4")?.status).toBe("rejected");
  });

  it("「第 N 段」 highlights the paragraph", async () => {
    const user = userEvent.setup();
    renderNovel();
    await screen.findByText("177 字 · 5 段");
    await user.click(within(card(4)).getByRole("button", { name: "第 4 段" }));
    expect(document.getElementById("novel-para-3")).toHaveAttribute("data-focused", "true");
    expect(document.getElementById("novel-para-0")).not.toHaveAttribute("data-focused");
  });

  it("the run bar follows the component picked in the Inspector", async () => {
    const user = userEvent.setup();
    renderNovel();
    await screen.findByText("当前产物 · 补全建议 · 4 条");
    await user.click(screen.getByRole("button", { name: "设定提取" }));
    expect(
      await screen.findByText("当前产物 · 设定卡 · 人物 2 · 地点 3 · 道具 4"),
    ).toBeInTheDocument();
    expect(screen.getByText(/v1 · Qwen3.6-27B/)).toBeInTheDocument();
  });

  it("goes on to the script step through the gate", async () => {
    const user = userEvent.setup();
    renderNovel();
    const gate = await screen.findByRole("button", { name: "确认原文，生成剧本" });
    await waitFor(() => expect(gate).toBeEnabled());
    await user.click(gate);
    expect(await screen.findByTestId("script-page")).toBeInTheDocument();
  });
});
