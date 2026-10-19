import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";

import { Toaster } from "@/components/ui/sonner";
import { getDb } from "@/mocks/db";
import NovelPage from "@/pages/Novel";
import { backend, fake } from "@/test/backend";
import { FakeEventSource } from "@/test/fakeEventSource";
import { fakeNovel } from "@/test/fakes/novel";
import { renderAt } from "@/test/render";

// The user's own words, typed into the page (content, not UI copy).
const INSTRUCTION = "别写风衣，她今天穿的是工装外套";

function renderNovel(series = "demo") {
  return renderAt(
    <>
      <Routes>
        <Route path="/s/:series/e/:ep/novel" element={<NovelPage />} />
        <Route path="/s/:series/e/:ep/script" element={<div data-testid="script-page" />} />
      </Routes>
      <Toaster />
    </>,
    `/s/${series}/e/1/novel`,
  );
}

/** A series made on the fake backend, without a novel. */
function newSeries(): string {
  fake.created.push({
    id: "s1",
    slug: "s1",
    title: "新剧",
    ui_lang: "zh-CN",
    created_at: "2026-10-19T10:00:00Z",
  });
  return "s1";
}

const novelFile = () => new File(["第一章 红伞\n那天雨下得很大。"], "雨停之前.txt");

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

  it("switches chapters; paragraphs are numbered across the book", async () => {
    const user = userEvent.setup();
    renderNovel();
    await screen.findByText("177 字 · 5 段");
    expect(screen.getByText("全书 3 章 · 2395 字")).toBeInTheDocument();
    const picker = screen.getByRole("combobox", { name: "章节" });
    expect(
      within(picker)
        .getAllByRole("option")
        .map((o) => o.textContent),
    ).toEqual(["第一章 红伞 · 147 字", "第二章 十二点 · 1017 字", "第三章 旧发圈 · 1231 字"]);
    await user.selectOptions(picker, "1");
    const first = await screen.findByText(/^楼道的声控灯还是不亮/);
    expect(first.closest("li")).toHaveTextContent(/^06/);
    expect(screen.getByText("1017 字 · 23 段")).toBeInTheDocument();
    expect(screen.queryByText(/^那天雨下得很大/)).toBeNull();
  });

  it("a suggestion in another chapter switches to it and highlights the paragraph", async () => {
    const user = userEvent.setup();
    const s4 = suggestion("s4");
    if (s4) s4.para_idx = 29;
    renderNovel();
    await screen.findByText("177 字 · 5 段");
    await user.click(screen.getByRole("button", { name: "第 30 段" }));
    expect(await screen.findByText(/^他从收银台底下摸出一个牛皮纸信封/)).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "章节" })).toHaveValue("2");
    expect(document.getElementById("novel-para-29")).toHaveAttribute("data-focused", "true");
  });

  it("a new series starts empty and imports a novel: preview, rights, import", async () => {
    const user = userEvent.setup();
    renderNovel(newSeries());
    expect(await screen.findByText("还没有导入小说")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "导入小说" }));
    const dialog = await screen.findByRole("dialog", { name: "导入小说" });
    await user.upload(within(dialog).getByTestId("novel-file"), novelFile());
    expect(await within(dialog).findByText("识别到 3 章 · 2395 字")).toBeInTheDocument();
    expect(within(dialog).getByText("UTF-8")).toBeInTheDocument();
    expect(within(dialog).getByText("第二章 十二点")).toBeInTheDocument();
    // Nothing to replace yet.
    expect(within(dialog).queryByText(/会替换现在的原文/)).toBeNull();
    const submit = within(dialog).getByRole("button", { name: "导入" });
    expect(submit).toBeDisabled();
    await user.click(within(dialog).getByRole("checkbox", { name: /改编权/ }));
    await user.click(submit);
    expect(await screen.findByText("已导入 雨停之前.txt：3 章 · 2395 字")).toBeInTheDocument();
    expect(await screen.findByText(/^那天雨下得很大/)).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(fakeNovel.uploads).toEqual([
      { series: "s1", filename: "雨停之前.txt", dryRun: true, rights: false },
      { series: "s1", filename: "雨停之前.txt", dryRun: false, rights: true },
    ]);
  });

  it("importing again says it replaces the current text", async () => {
    const user = userEvent.setup();
    renderNovel();
    await screen.findByText("177 字 · 5 段");
    await user.click(screen.getByRole("button", { name: "导入 .txt / .docx" }));
    const dialog = await screen.findByRole("dialog", { name: "导入小说" });
    await user.upload(within(dialog).getByTestId("novel-file"), novelFile());
    expect(
      await within(dialog).findByText(/会替换现在的原文（雨停之前.txt）：旧文本留在历史里/),
    ).toBeInTheDocument();
  });

  it("a file that cannot be imported is explained in the dialog", async () => {
    const user = userEvent.setup({ applyAccept: false });
    renderNovel();
    await screen.findByText("177 字 · 5 段");
    await user.click(screen.getByRole("button", { name: "导入 .txt / .docx" }));
    const dialog = await screen.findByRole("dialog", { name: "导入小说" });
    await user.upload(within(dialog).getByTestId("novel-file"), new File(["%PDF"], "a.pdf"));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "只支持 .txt 和 .docx（这个文件是 .pdf）",
    );
    expect(within(dialog).getByRole("button", { name: "导入" })).toBeDisabled();
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
