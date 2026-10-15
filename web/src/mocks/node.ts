import { setupServer } from "msw/node";

import { handlers } from "@/mocks/handlers";

/** The same demo handlers for Vitest (see test/setup.ts). */
export const server = setupServer(...handlers);
