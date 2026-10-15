import { screen } from "@testing-library/react";

import { AppRoutes } from "@/app/routes";
import { renderAt } from "@/test/render";

vi.mock("@/legacy/App", () => ({ default: () => <div>legacy app</div> }));

describe("/legacy", () => {
  it("warns that legacy calls bypass accounting and budgets", async () => {
    renderAt(<AppRoutes />, "/legacy");
    expect(screen.getByRole("note")).toHaveTextContent("旧界面：调用不记账、不受预算限制");
    expect(await screen.findByText("legacy app")).toBeInTheDocument();
  });
});
