import { http, passthrough } from "msw";

import { ShotPatchSchema } from "@/api/schemas/shots";
import { getDb } from "@/mocks/db";
import { demoError, demoJson, v1 } from "@/mocks/http";

export function confirmedShotCount(episodeId: string): { done: number; total: number } {
  const list = getDb().shots.filter((s) => s.episode_id === episodeId);
  return { done: list.filter((s) => s.confirmed).length, total: list.length };
}

export const shotHandlers = [
  http.get(v1("/episodes/:id/shots"), ({ params }) => {
    // Only the demo's episode 1 has shots here (until M4 step 5); any other episode's are the
    // backend's (M4 step 2).
    const mine = getDb().shots.filter((s) => s.episode_id === String(params.id));
    if (!mine.length) return passthrough();
    return demoJson(mine);
  }),

  http.patch(v1("/shots/:id"), async ({ params, request }) => {
    const shot = getDb().shots.find((s) => s.id === String(params.id));
    if (!shot) return passthrough();
    const body = ShotPatchSchema.safeParse(await request.json());
    if (!body.success) return demoError(422, "invalid_request", { issues: body.error.message });
    Object.assign(shot, body.data);
    // Confirming a shot adopts the keyframe on screen (SPEC 4.2: 下游用已采纳的版本).
    const kf = shot.keyframe_product_id ? getDb().products[shot.keyframe_product_id] : undefined;
    if (body.data.confirmed && kf?.current_version_id && kf.adopted_version_id === null) {
      kf.adopted_version_id = kf.current_version_id;
      kf.status = "adopted";
    }
    return demoJson(shot);
  }),
];
