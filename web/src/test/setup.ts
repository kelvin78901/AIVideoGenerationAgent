import "@testing-library/jest-dom/vitest";

import { resetDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { useDemoStore } from "@/stores/demo";

// Demo handlers answer unimplemented endpoints; anything else must be mocked by the test itself.
beforeAll(() => server.listen({ onUnhandledRequest: "bypass" }));
afterEach(() => {
  server.resetHandlers();
  resetDb();
  useDemoStore.getState().reset();
});
afterAll(() => server.close());
