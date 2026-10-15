import { http } from "msw";

import { getDb } from "@/mocks/db";
import { demoError, demoJson, v1 } from "@/mocks/http";

export const seriesHandlers = [
  http.get(v1("/series/:id"), ({ params }) => {
    const series = getDb().series[String(params.id)];
    return series ? demoJson(series) : demoError(404, "series_not_found", { id: params.id });
  }),
];
