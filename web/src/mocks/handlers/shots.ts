import { http, passthrough } from "msw";

import type { Shot } from "@/api/schemas/shots";
import { backendJson } from "@/mocks/backend";
import { getDb } from "@/mocks/db";
import { EP1 } from "@/mocks/fixtures/demo/episodes";
import { demoJson, v1 } from "@/mocks/http";

/**
 * Shots are the backend's since M4. Until video takes are (M5), the demo lays episode 1's takes
 * over them (each shot's `video_product_id`), and the generate and post demos read the shots
 * from here, so a duration changed on the storyboard moves the timeline.
 */
function withTakes(episodeId: string, shots: Shot[]): Shot[] {
  const videos = Object.values(getDb().products).filter((p) => p.slot === "video");
  const laid = shots.map((s) => ({
    ...s,
    video_product_id: videos.find((p) => p.owner_id === s.id)?.id ?? s.video_product_id,
  }));
  const db = getDb();
  db.shots = [...db.shots.filter((s) => s.episode_id !== episodeId), ...laid];
  return laid;
}

/**
 * The backend's shots of a demo episode with the demo's takes on them, remembered for the
 * handlers that read them synchronously (`getDb().shots`); the last known ones when the backend
 * is down.
 */
export async function demoShots(request: Request, episodeId: string = EP1): Promise<Shot[]> {
  const url = new URL(`/api/v1/episodes/${encodeURIComponent(episodeId)}/shots`, request.url);
  const real = await backendJson<Shot[] | null>(new Request(url), null);
  return real
    ? withTakes(episodeId, real)
    : getDb().shots.filter((s) => s.episode_id === episodeId);
}

export const shotHandlers = [
  http.get(v1("/episodes/:id/shots"), async ({ params, request }) => {
    // Only episode 1 has takes; any other episode's shots are the backend's alone.
    const id = String(params.id);
    if (id !== EP1) return passthrough();
    const real = await backendJson<Shot[] | null>(request.clone(), null);
    if (!real) return passthrough(); // backend down: let the page show the error
    return demoJson(withTakes(id, real));
  }),
];
