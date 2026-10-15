import { http } from "msw";

import { GATE_STEP, GateSchema } from "@/api/schemas/gates";
import { getDb } from "@/mocks/db";
import { demoError, demoJson, v1 } from "@/mocks/http";

function decide(action: "confirm" | "reopen") {
  return http.post(v1(`/gates/:gate/${action}`), async ({ params, request }) => {
    const gate = GateSchema.safeParse(params.gate);
    if (!gate.success) return demoError(404, "unknown_gate", { gate: params.gate });
    const body = (await request.json()) as { scope_id?: unknown };
    const scopeId = String(body.scope_id ?? "");
    const step = getDb().progress[scopeId]?.steps[GATE_STEP[gate.data]];
    if (!step) return demoError(404, "episode_not_found", { id: scopeId });
    step.state = action === "confirm" ? "confirmed" : "in_progress";
    const decision = {
      id: `demo-gate-${getDb().gates.length + 1}`,
      gate: gate.data,
      scope_id: scopeId,
      action,
      decided_at: new Date().toISOString(),
    };
    getDb().gates.push(decision);
    return demoJson(decision);
  });
}

export const gateHandlers = [decide("confirm"), decide("reopen")];
