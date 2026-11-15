import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";

import { Toaster } from "@/components/ui/sonner";
import SpecPage from "@/pages/Spec";
import { backend } from "@/test/backend";
import { fakePictures } from "@/test/fakes/pictures";
import { renderAt } from "@/test/render";

/** 风格板 on the output spec page (M5.5 step 16b, Kelvin 2026-11-10). */

const renderSpec = () =>
  renderAt(
    <Routes>
      <Route
        path="/s/:series/spec"
        element={
          <>
            <SpecPage />
            <Toaster />
          </>
        }
      />
    </Routes>,
    "/s/demo/spec",
  );

beforeEach(() => backend());

describe("风格板", () => {
  it("adds pictures of the series' look, up to four", async () => {
    const user = userEvent.setup();
    renderSpec();
    const board = await screen.findByRole("group", { name: "风格板" });
    expect(screen.getByRole("heading", { name: "风格板" })).toBeInTheDocument();
    // One purpose only: nothing to choose.
    expect(within(board).queryByRole("combobox")).not.toBeInTheDocument();
    const input = within(board).getByLabelText("选一张图片加进风格板");
    for (const name of ["a.png", "b.png", "c.png", "d.png"])
      await user.upload(input, new File(["png"], name, { type: "image/png" }));
    await waitFor(() => expect(within(board).getAllByRole("img")).toHaveLength(4));
    expect(within(board).getByRole("button", { name: "上传风格图" })).toBeDisabled();
    expect(board).toHaveTextContent("最多 4 张，删掉一张再加");
    const p = fakePictures.products.find((x) => x.slot === "style_board");
    expect(p?.owner_id).toBe("demo");
    expect(p?.versions.at(-1)?.files.map((f) => f.purpose)).toEqual([
      "style",
      "style",
      "style",
      "style",
    ]);
  });
});
