import type { Product } from "@/api/schemas/products";
import type { Shot } from "@/api/schemas/shots";
import { backendJson } from "@/mocks/backend";
import { getDb } from "@/mocks/db";
import { EP1 } from "@/mocks/fixtures/demo/episodes";

/**
 * Shots (M4) and their video takes (M5) are the backend's. The post demo reads them from here
 * (`handlers/post.ts`), so a duration changed on the storyboard moves the timeline and an
 * adopted take fills its clip.
 */

/**
 * The backend's shots of a demo episode, remembered for the handlers that read them
 * synchronously (`getDb().shots`); the last known ones when the backend is down.
 */
export async function demoShots(request: Request, episodeId: string = EP1): Promise<Shot[]> {
  const url = new URL(`/api/v1/episodes/${encodeURIComponent(episodeId)}/shots`, request.url);
  const real = await backendJson<Shot[] | null>(new Request(url), null);
  if (!real) return getDb().shots.filter((s) => s.episode_id === episodeId);
  const db = getDb();
  db.shots = [...db.shots.filter((s) => s.episode_id !== episodeId), ...real];
  return real;
}

/** The backend's video products (one per shot), remembered like the shots (`getDb().videos`). */
export async function demoVideos(request: Request): Promise<Product[]> {
  const url = new URL("/api/v1/products?component=vid", request.url);
  const real = await backendJson<Product[] | null>(new Request(url), null);
  if (real) getDb().videos = real;
  return getDb().videos;
}
