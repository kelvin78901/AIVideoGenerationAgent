import { http, passthrough } from "msw";

import { GATE_STEP, GateSchema } from "@/api/schemas/gates";
import { getDb } from "@/mocks/db";
import { demoError, demoJson, v1 } from "@/mocks/http";

/** The backend's gates (M2–M4); the demo answers 生成 and 后期 until their milestones. */
const BACKEND_GATES = new Set<string>(["novel", "script", "assets", "storyboard"]);

function decide(action: "confirm" | "reopen") {
  return http.post(v1(`/gates/:gate/${action}`), async ({ params, request }) => {
    if (BACKEND_GATES.has(String(params.gate))) return passthrough();
    const gate = GateSchema.safeParse(params.gate);
    if (!gate.success) return demoError(404, "unknown_gate", { gate: params.gate });
    const body = (await request.json()) as { scope_id?: unknown };
    const scopeId = String(body.scope_id ?? "");
    const steps = getDb().progress[scopeId];
    const id = GATE_STEP[gate.data];
    const step = steps && (id === "generate" || id === "post") ? steps[id] : undefined;
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
