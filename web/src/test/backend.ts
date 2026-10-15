import { http, HttpResponse } from "msw";

import { server } from "@/mocks/node";

/** Real backend endpoints the picker reads: live mode, DeepSeek without a key. */
export function backend({ mock = true }: { mock?: boolean } = {}) {
  server.use(
    http.get("*/api/v1/health", () => HttpResponse.json({ status: "ok", version: "0", mock })),
    http.get("*/api/v1/providers", () =>
      HttpResponse.json({
        providers: [
          {
            id: "deepseek",
            name: "DeepSeek",
            where: "api",
            base_url: null,
            docs: null,
            verify: true,
            needs_key: true,
            has_key: false,
            key_source: "none",
            enabled: true,
            models: [
              {
                key: "deepseek/v4-pro",
                display: "x",
                model_id: null,
                price: null,
                json_mode: true,
              },
            ],
          },
        ],
        llm_ui_order: [],
      }),
    ),
  );
}
