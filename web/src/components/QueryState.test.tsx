import { useQuery } from "@tanstack/react-query";
import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { QueryState } from "@/components/QueryState";
import i18n from "@/i18n";
import { renderAt } from "@/test/render";

/** An upstream query (like `/series`) and one that needs its result as a key. */
function Chain({ upstream }: { upstream: () => Promise<{ id: string }> }) {
  const parent = useQuery({ queryKey: ["parent"], queryFn: upstream });
  const id = parent.data?.id;
  const child = useQuery({
    queryKey: ["child", id],
    queryFn: () => Promise.resolve(`child of ${id}`),
    enabled: !!id,
  });
  return <QueryState query={child}>{(text) => <p>{text}</p>}</QueryState>;
}

beforeEach(async () => {
  await act(() => i18n.changeLanguage("zh-CN"));
});

describe("QueryState", () => {
  it("shows a skeleton while the query it depends on is loading, then the data", async () => {
    let resolve: (v: { id: string }) => void = () => {};
    renderAt(<Chain upstream={() => new Promise((r) => (resolve = r))} />);
    expect(screen.getByRole("status", { name: "正在加载" })).toBeInTheDocument();
    expect(screen.queryByTestId("query-blocked")).not.toBeInTheDocument();
    act(() => resolve({ id: "ep1" }));
    expect(await screen.findByText("child of ep1")).toBeInTheDocument();
  });

  it("does not stay a skeleton forever when the query it depends on failed", async () => {
    const user = userEvent.setup();
    let fail = true;
    renderAt(
      <Chain
        upstream={() => (fail ? Promise.reject(new Error("boom")) : Promise.resolve({ id: "ep1" }))}
      />,
    );
    expect(await screen.findByTestId("query-blocked")).toHaveTextContent(
      "没有可显示的内容：它依赖的数据没加载到",
    );
    expect(screen.queryByRole("status", { name: "正在加载" })).not.toBeInTheDocument();
    fail = false;
    await user.click(screen.getByRole("button", { name: "重试" }));
    expect(await screen.findByText("child of ep1")).toBeInTheDocument();
  });
});
