import { http } from "msw";

import { getDb } from "@/mocks/db";
import { demoJson, v1 } from "@/mocks/http";

export const metricsHandlers = [
  // ?scope=episode&episode=<id> | ?scope=series&series=<id>
  http.get(v1("/metrics/summary"), ({ request }) => {
    const scope =
      new URL(request.url).searchParams.get("scope") === "series" ? "series" : "episode";
    return demoJson(getDb().summary[scope]);
  }),
];
