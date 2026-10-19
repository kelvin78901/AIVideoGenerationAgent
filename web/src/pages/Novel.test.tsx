import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";

import { Toaster } from "@/components/ui/sonner";
import NovelPage from "@/pages/Novel";
import { backend, fake } from "@/test/backend";
import { FakeEventSource } from "@/test/fakeEventSource";
import { fakeBible } from "@/test/fakes/bible";
import { fakeNovel } from "@/test/fakes/novel";
import { fakeSuggestions } from "@/test/fakes/suggestions";
import { renderAt } from "@/test/render";

// The user's own words, typed into the page (content, not UI copy).
const INSTRUCTION = "别写风衣，她今天穿的是工装外套";

function renderNovel(series = "demo", query = "") {
  return renderAt(
    <>
      <Routes>
        <Route path="/s/:series/e/:ep/novel" element={<NovelPage />} />
        <Route path="/s/:series/e/:ep/script" element={<div data-testid="script-page" />} />
      </Routes>
      <Toaster />
    </>,
    `/s/${series}/e/1/novel${query}`,
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
const suggestion = (id: string) => fakeSuggestions.data.suggestions.find((s) => s.id === id);

beforeEach(() => {
  vi.stubGlobal("EventSource", FakeEventSource);
  backend();
});
afterEach(() => vi.unstubAllGlobals());

describe("NovelPage", () => {
  it("「在剧本里」: the script lines a paragraph went into, each a link to the script", async () => {
    const user = userEvent.setup();
    renderNovel();
    await screen.findByText("177 字 · 5 段");
    await user.click(screen.getByRole("button", { name: "第 2 段在剧本里的位置" }));
    const trace = screen.getByRole("region", { name: "第 2 段在剧本里" });
    const links = await within(trace).findAllByRole("link");
    expect(links.map((a) => a.getAttribute("href"))).toEqual(
      ["demo-b3", "demo-b5", "demo-b6", "demo-b10"].map((id) => `/s/demo/e/1/script?line=${id}`),
    );
    expect(links[0]).toHaveTextContent("第 1 集 · 场 1△ 门口靠着一把红色长柄伞");
    expect(links[3]).toHaveTextContent("第 1 集 · 场 2林晚（OS）：三年了。他凭什么。");
    await user.click(within(trace).getByRole("button", { name: "收起" }));
    expect(screen.queryByRole("region", { name: "第 2 段在剧本里" })).not.toBeInTheDocument();
  });

  it("opens at the paragraph a link points at, with 「在剧本里」", async () => {
    renderNovel("demo", "?para=4");
    const trace = await screen.findByRole("region", { name: "第 5 段在剧本里" });
    expect(await within(trace).findByRole("link")).toHaveAttribute(
      "href",
      "/s/demo/e/1/script?line=demo-b12",
    );
    expect(document.getElementById("novel-para-4")).toHaveAttribute("data-focused");
  });

  it("shows the text with the adopted addition, counts and the bible", async () => {
    renderNovel();
    expect(await screen.findByText("177 字 · 5 段")).toBeInTheDocument();
    expect(screen.getByText("已采纳 1 / 4")).toBeInTheDocument();
    const added = screen.getByText(/她的米色风衣湿了半边/, { selector: "mark" });
    expect(added).toHaveTextContent("＋");
    expect(screen.getByRole("list", { name: "人物" })).toHaveTextContent("林晚 · 26 岁 · 插画师");
    expect(
      within(screen.getByRole("list", { name: "道具" })).getAllByRole("listitem"),
    ).toHaveLength(6);
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

  it("a rewrite over the per-call cap waits for the user's yes", async () => {
    fakeSuggestions.overBudget = { estimate_usd: 0.0012, limit_usd: 0.001 };
    const user = userEvent.setup();
    renderNovel();
    await screen.findByText("177 字 · 5 段");
    const lighting = card(1, 1);
    await user.click(within(lighting).getByRole("button", { name: "改写要求" }));
    await user.type(within(lighting).getByLabelText("告诉 AI 这一条怎么改"), "写成灯一闪一闪的");
    await user.click(within(lighting).getByRole("button", { name: "按要求重写这一条" }));
    const alert = await within(lighting).findByRole("alert");
    expect(alert).toHaveTextContent("预计 $0.0012，超过上限 $0.001，确认后才会发出");
    expect(suggestion("s2")?.rewrite_instruction).toBeNull();
    await user.click(within(alert).getByRole("button", { name: "确认花费，重写" }));
    expect(await within(lighting).findByText("已按要求重写")).toBeInTheDocument();
    expect(fakeSuggestions.requests.map((r) => r.action === "rewrite" && r.confirm_budget)).toEqual(
      [false, true],
    );
  });

  it("marks suggestions that are not adopted yet", async () => {
    fakeSuggestions.data.adopted = false;
    renderNovel();
    expect(await screen.findByText("未采纳")).toBeInTheDocument();
    expect(screen.getByText(/这一版还没采纳：设定提取和分集规划/)).toBeInTheDocument();
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
    expect(screen.getByText("全书 3 章 · 3006 字")).toBeInTheDocument();
    const picker = screen.getByRole("combobox", { name: "章节" });
    expect(
      within(picker)
        .getAllByRole("option")
        .map((o) => o.textContent),
    ).toEqual(["第一章 红伞 · 147 字", "第二章 十二点 · 1274 字", "第三章 旧发圈 · 1585 字"]);
    await user.selectOptions(picker, "1");
    const first = await screen.findByText(/^楼道的声控灯还是不亮/);
    expect(first.closest("li")).toHaveTextContent(/^06/);
    expect(screen.getByText("1274 字 · 26 段")).toBeInTheDocument();
    expect(screen.queryByText(/^那天雨下得很大/)).toBeNull();
  });

  it("a suggestion in another chapter switches to it and highlights the paragraph", async () => {
    const user = userEvent.setup();
    const s4 = suggestion("s4");
    if (s4) s4.para_idx = 32;
    renderNovel();
    await screen.findByText("177 字 · 5 段");
    await user.click(screen.getByRole("button", { name: "第 33 段" }));
    expect(await screen.findByText(/^他从收银台底下摸出一个牛皮纸信封/)).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "章节" })).toHaveValue("2");
    expect(document.getElementById("novel-para-32")).toHaveAttribute("data-focused", "true");
  });

  it("a new series starts empty and imports a novel: preview, rights, import", async () => {
    const user = userEvent.setup();
    renderNovel(newSeries());
    expect(await screen.findByText("还没有导入小说")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "导入小说" }));
    const dialog = await screen.findByRole("dialog", { name: "导入小说" });
    await user.upload(within(dialog).getByTestId("novel-file"), novelFile());
    expect(await within(dialog).findByText("识别到 3 章 · 3006 字")).toBeInTheDocument();
    expect(within(dialog).getByText("UTF-8")).toBeInTheDocument();
    expect(within(dialog).getByText("第二章 十二点")).toBeInTheDocument();
    // Nothing to replace yet.
    expect(within(dialog).queryByText(/会替换现在的原文/)).toBeNull();
    const submit = within(dialog).getByRole("button", { name: "导入" });
    expect(submit).toBeDisabled();
    await user.click(within(dialog).getByRole("checkbox", { name: /改编权/ }));
    await user.click(submit);
    expect(await screen.findByText("已导入 雨停之前.txt：3 章 · 3006 字")).toBeInTheDocument();
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
      await screen.findByText("当前产物 · 设定卡 · 人物 3 · 地点 4 · 道具 6"),
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

  describe("提取到的设定", () => {
    const entry = (name: RegExp) => screen.getByRole("button", { name });

    it("marks an entry's paragraphs, in the chapter they are in", async () => {
      const user = userEvent.setup();
      renderNovel();
      await screen.findByText("177 字 · 5 段");
      await user.click(entry(/^旧小票/));
      expect(entry(/^旧小票/)).toHaveAttribute("aria-pressed", "true");
      // Paragraphs 34, 41 and 42 are in chapter 3: the page switches there.
      expect(await screen.findByRole("option", { name: /第三章/, selected: true })).toBeTruthy();
      await waitFor(() => expect(document.querySelectorAll("[data-marked]")).toHaveLength(3));
      expect(document.getElementById("novel-para-33")).toHaveAttribute("data-marked");
      expect(screen.getByText("「旧小票」在原文里出现 3 段，已在左边标出。")).toBeInTheDocument();
      await user.click(entry(/^旧小票/));
      expect(document.querySelectorAll("[data-marked]")).toHaveLength(0);
    });

    it("edits and freezes an entry", async () => {
      const user = userEvent.setup();
      renderNovel();
      await screen.findByText("177 字 · 5 段");
      await user.click(screen.getByRole("button", { name: "编辑「林晚」" }));
      const dialog = await screen.findByRole("dialog", { name: "编辑设定" });
      const summary = within(dialog).getByLabelText("简介");
      await user.clear(summary);
      await user.type(summary, "27 岁 · 插画师");
      await user.click(within(dialog).getByLabelText(/冻结/));
      await user.click(within(dialog).getByRole("button", { name: "保存" }));
      expect(await screen.findByText("已保存「林晚」。")).toBeInTheDocument();
      expect(fakeBible.edits).toEqual([
        {
          id: "c-linwan",
          data: expect.objectContaining({ summary: "27 岁 · 插画师" }) as unknown,
          frozen: true,
        },
      ]);
      expect(await screen.findByRole("list", { name: "人物" })).toHaveTextContent(
        "林晚 · 27 岁 · 插画师已冻结",
      );
    });

    it("splits an alias off into an entry of its own", async () => {
      const user = userEvent.setup();
      renderNovel();
      await screen.findByText("177 字 · 5 段");
      await user.click(screen.getByRole("button", { name: "编辑「楼下便利店」" }));
      const dialog = await screen.findByRole("dialog", { name: "编辑设定" });
      await user.click(within(dialog).getByRole("button", { name: "把「便利店」拆成单独一条" }));
      expect(await screen.findByText("已把「便利店」拆成单独一条。")).toBeInTheDocument();
      expect(fakeBible.edits).toEqual([{ action: "split", ids: ["l-store"], alias: "便利店" }]);
      expect(
        await within(screen.getByRole("list", { name: "地点" })).findByRole("button", {
          name: /^便利店/,
        }),
      ).toBeInTheDocument();
    });

    it("merges what may be the same, or keeps them apart", async () => {
      const user = userEvent.setup();
      renderNovel();
      const same = await screen.findByRole("group", { name: "可能是同一个" });
      expect(same).toHaveTextContent("「旧发圈」和「黑色发圈」");
      expect(same).toHaveTextContent("小票上的黑色发圈就是她手腕上戴了三年的那根旧发圈。");
      // The one the text mentions more stays.
      await user.click(
        within(same).getByRole("button", { name: "把「黑色发圈」合并进「旧发圈」" }),
      );
      expect(
        await screen.findByText("已合并：「黑色发圈」现在是「旧发圈」的别名。"),
      ).toBeInTheDocument();
      expect(fakeBible.edits).toEqual([{ action: "merge", ids: ["p-hairtie", "p-black-hairtie"] }]);
      await waitFor(() => expect(screen.queryByRole("group", { name: "可能是同一个" })).toBeNull());
      expect(screen.getByRole("list", { name: "道具" })).not.toHaveTextContent("黑色发圈");
    });

    it("「不是同一个」 drops the suggestion", async () => {
      const user = userEvent.setup();
      renderNovel();
      const same = await screen.findByRole("group", { name: "可能是同一个" });
      await user.click(
        within(same).getByRole("button", { name: "「旧发圈」和「黑色发圈」不是同一个" }),
      );
      await waitFor(() => expect(screen.queryByRole("group", { name: "可能是同一个" })).toBeNull());
      expect(fakeBible.edits).toEqual([
        { action: "distinct", ids: ["p-hairtie", "p-black-hairtie"] },
      ]);
      expect(screen.getByRole("list", { name: "道具" })).toHaveTextContent("黑色发圈");
    });

    it("says when the version on screen is not adopted, and when nothing was extracted", async () => {
      fakeBible.bible.adopted = false;
      const { unmount } = renderNovel();
      expect(await screen.findByText("未采纳")).toBeInTheDocument();
      expect(
        screen.getByText("这一版还没采纳：剧本和素材两步仍用之前采纳的那一版。"),
      ).toBeInTheDocument();
      unmount();
      fakeBible.bible.entities = [];
      fakeBible.bible.merge_suggestions = [];
      renderNovel();
      expect(
        await screen.findByText("还没有提取设定。点上面的「重跑」让 AI 从原文里找一遍。"),
      ).toBeInTheDocument();
    });
  });

  describe("逐段编辑", () => {
    async function original() {
      const user = userEvent.setup();
      renderNovel();
      await screen.findByText("177 字 · 5 段");
      await user.click(screen.getByRole("radio", { name: "原文" }));
      return user;
    }

    it("edits a paragraph and saves the whole chapter", async () => {
      const user = await original();
      await user.click(screen.getByRole("button", { name: "改第 2 段" }));
      const box = screen.getByLabelText("第 2 段的文字");
      expect(screen.getByText("保存后小说补全、设定提取会变成待更新。")).toBeInTheDocument();
      await user.clear(box);
      expect(screen.getByRole("button", { name: "保存" })).toBeDisabled();
      await user.type(box, "家门口靠着一把红伞。");
      await user.click(screen.getByRole("button", { name: "保存" }));
      expect(await screen.findByText("家门口靠着一把红伞。")).toBeInTheDocument();
      expect(screen.queryByLabelText("第 2 段的文字")).toBeNull();
      const [sent] = fakeNovel.edits;
      expect(sent?.idx).toBe(0);
      expect(sent?.title).toBe("第一章 红伞");
      expect(sent?.paragraphs).toHaveLength(5);
      expect(sent?.paragraphs[1]).toBe("家门口靠着一把红伞。");
      expect(
        await screen.findByText("已保存，出了一个新的小说版本（旧文本留在历史里）。"),
      ).toBeInTheDocument();
    });

    it("inserts and deletes paragraphs", async () => {
      const user = await original();
      await user.click(screen.getByRole("button", { name: "在第 1 段后插入一段" }));
      await user.type(screen.getByLabelText("第 1 段后的新段落"), "楼道里很黑。");
      await user.click(screen.getByRole("button", { name: "保存" }));
      expect(await screen.findByText(/· 6 段$/)).toBeInTheDocument();
      expect(screen.getByText("楼道里很黑。").closest("li")).toHaveTextContent(/^02/);
      await user.click(screen.getByRole("button", { name: "删除第 6 段" }));
      const confirm = screen.getByRole("alert");
      expect(confirm).toHaveTextContent("删除第 6 段？");
      await user.click(within(confirm).getByRole("button", { name: "删除" }));
      expect(await screen.findByText(/· 5 段$/)).toBeInTheDocument();
      expect(screen.queryByText(/^最后，她还是拿起了那把伞/)).toBeNull();
      expect(fakeNovel.edits.map((e) => e.paragraphs.length)).toEqual([6, 5]);
    });

    it("retitles the chapter", async () => {
      const user = await original();
      await user.click(screen.getByRole("button", { name: "改标题" }));
      const title = screen.getByLabelText("章节标题");
      await user.clear(title);
      await user.type(title, "第一章 一把红伞");
      await user.click(screen.getByRole("button", { name: "保存" }));
      expect(await screen.findByRole("option", { name: /^第一章 一把红伞/ })).toBeInTheDocument();
      expect(fakeNovel.edits[0]).toMatchObject({ idx: 0, title: "第一章 一把红伞" });
    });

    it("only in 原文: the other views show additions, not the author's text", async () => {
      renderNovel();
      await screen.findByText("177 字 · 5 段");
      expect(screen.getByText("要改原文，切到「原文」。")).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "改第 1 段" })).toBeNull();
      expect(screen.queryByRole("button", { name: "改标题" })).toBeNull();
    });

    it("not while the novel is locked", async () => {
      const novel = fakeBible.products.find((p) => p.slot === "novel");
      if (novel) novel.locked_hash = "sha256:x";
      const user = userEvent.setup();
      renderNovel();
      await screen.findByText("177 字 · 5 段");
      await user.click(screen.getByRole("radio", { name: "原文" }));
      expect(screen.queryByRole("button", { name: "改第 1 段" })).toBeNull();
      expect(screen.queryByText("要改原文，切到「原文」。")).toBeNull();
    });
  });
});
