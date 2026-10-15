import { http } from "msw";

import { ShotPatchSchema } from "@/api/schemas/shots";
import { getDb } from "@/mocks/db";
import { demoError, demoJson, v1 } from "@/mocks/http";

export function confirmedShotCount(episodeId: string): { done: number; total: number } {
  const list = getDb().shots.filter((s) => s.episode_id === episodeId);
  return { done: list.filter((s) => s.confirmed).length, total: list.length };
}

export const shotHandlers = [
  http.get(v1("/episodes/:id/shots"), ({ params }) => {
    const id = String(params.id);
    if (!getDb().episodes.some((e) => e.id === id))
      return demoError(404, "episode_not_found", { id });
    return demoJson(getDb().shots.filter((s) => s.episode_id === id));
  }),

  http.patch(v1("/shots/:id"), async ({ params, request }) => {
    const shot = getDb().shots.find((s) => s.id === String(params.id));
    if (!shot) return demoError(404, "shot_not_found", { id: params.id });
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
