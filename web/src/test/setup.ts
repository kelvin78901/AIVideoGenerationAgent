import "@testing-library/jest-dom/vitest";

import { resetDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { useDemoStore } from "@/stores/demo";
import { useInspectorStore } from "@/stores/inspector";

// jsdom has no ResizeObserver; Radix (Slider) only needs it to exist.
globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
};

// jsdom's FormData and File are not the ones Node's fetch (undici) knows, so an upload would go
// out as "[object FormData]". Use Node's own: FormData from a form undici parses, File from
// node:buffer (no @types/node here, hence the casts).
const nodeForm = await new Response(new URLSearchParams("a=1")).formData();
const node = (globalThis as unknown as { process: { getBuiltinModule(id: string): unknown } })
  .process;
globalThis.FormData = nodeForm.constructor as typeof FormData;
globalThis.File = (node.getBuiltinModule("node:buffer") as { File: typeof File }).File;

// Demo handlers answer unimplemented endpoints; anything else must be mocked by the test itself.
beforeAll(() => server.listen({ onUnhandledRequest: "bypass" }));
afterEach(() => {
  server.resetHandlers();
  resetDb();
  useDemoStore.getState().reset();
  useInspectorStore.getState().reset();
});
afterAll(() => server.close());
