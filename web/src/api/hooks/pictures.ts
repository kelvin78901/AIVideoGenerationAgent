/**
 * 图片来源与编辑 (M5.5): a picture of the user's own as a shot's keyframe, and 以这张为底重画 /
 * 局部修复 / 放大 of any picture of a keyframe, a reference picture or a views set. Each makes a
 * new version of the same product (history keeps the old one).
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";

import { del, post, postForm } from "@/api/client";
import { productKeys } from "@/api/hooks/products";
import { shotKeys } from "@/api/hooks/shots";
import { JobSchema, type Job } from "@/api/schemas/jobs";
import { ProductSchema, type Product } from "@/api/schemas/products";
import type { Where } from "@/api/schemas/common";

const enc = encodeURIComponent;

/** A box in the picture's own pixels. */
export interface CropBox {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** 「上传图片…」 on a shot's 首帧: cut to the box, at the delivery size, one candidate, picked. */
export function useUploadKeyframe(shotId: string, episodeId: string | undefined) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ file, box }: { file: File; box: CropBox | null }) => {
      const form = new FormData();
      form.append("file", file);
      if (box) for (const [k, v] of Object.entries(box)) form.append(k, String(Math.round(v)));
      return postForm(`/shots/${enc(shotId)}/keyframe/upload`, ProductSchema, form);
    },
    onSuccess: (product) => {
      client.setQueryData(productKeys.detail(product.id), product);
      void client.invalidateQueries({ queryKey: ["products", "list"] });
      // The shot's pick and picture changed.
      if (episodeId) void client.invalidateQueries({ queryKey: shotKeys.list(episodeId) });
    },
  });
}

export interface RedrawRequest {
  versionId: string;
  idx: number;
  prompt: string;
  /** 改动幅度, 0.1 a touch … 1.0 drawn anew. */
  strength: number;
  where?: Where;
}

export interface InpaintRequest {
  versionId: string;
  idx: number;
  prompt: string;
  /** Black, painted white where the picture changes; the picture's shape. */
  mask: Blob;
  where?: Where;
}

/** The run's job; the product turns `running` and the new version arrives with an event. */
function useVersionRun<V extends { productId: string }>(fn: (vars: V) => Promise<Job>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: (_job, vars) =>
      client.invalidateQueries({ queryKey: productKeys.detail(vars.productId) }),
  });
}

/** 以这张为底重画 (`POST /versions/{id}/redraw`). */
export function useRedraw() {
  return useVersionRun((r: RedrawRequest & { productId: string }) =>
    post(`/versions/${enc(r.versionId)}/redraw`, JobSchema, {
      idx: r.idx,
      prompt: r.prompt.trim() || null,
      strength: r.strength,
      ...(r.where ? { where: r.where } : {}),
    }),
  );
}

/** 局部修复 (`POST /versions/{id}/inpaint`, multipart with the mask). */
export function useInpaint() {
  return useVersionRun((r: InpaintRequest & { productId: string }) => {
    const form = new FormData();
    form.append("mask", r.mask, "mask.png");
    form.append("idx", String(r.idx));
    if (r.prompt.trim()) form.append("prompt", r.prompt.trim());
    if (r.where) form.append("where", r.where);
    return postForm(`/versions/${enc(r.versionId)}/inpaint`, JobSchema, form);
  });
}

/** 放大 (`POST /versions/{id}/upscale {idx}`, component `iup`, only locally). */
export function useUpscalePicture() {
  return useVersionRun((r: { productId: string; versionId: string; idx: number }) =>
    post(`/versions/${enc(r.versionId)}/upscale`, JobSchema, { idx: r.idx }),
  );
}

const ViewReplaceSchema = z.object({
  /** After an upload: the views set's new version, adopted. */
  product: ProductSchema.nullable().optional(),
  /** 重画这一张: the run drawing that one view. */
  job: JobSchema.nullable().optional(),
});

/** 六视图换一张 (`POST /products/{id}/views/{view}`): with a file, it takes that view's place;
 * without, that view is drawn again (409 `views_outdated` when the set follows an older locked
 * picture: the whole set is redrawn instead). The other five are copied either way. */
export function useReplaceView(assetId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ productId, view, file }: { productId: string; view: string; file?: File }) => {
      const form = new FormData();
      if (file) form.append("file", file);
      return postForm(`/products/${enc(productId)}/views/${enc(view)}`, ViewReplaceSchema, form);
    },
    onSuccess: (out, vars) => {
      if (out.product) client.setQueryData(productKeys.detail(out.product.id), out.product);
      else void client.invalidateQueries({ queryKey: productKeys.detail(vars.productId) });
      void client.invalidateQueries({ queryKey: productKeys.list({ owner: `asset:${assetId}` }) });
    },
  });
}

/** Where a picture set (镜头参考图, 风格板, 多参考图) is added to and removed from. */
interface SetEndpoint {
  /** `/shots/{id}/refs`, `/series/{id}/style-board`, `/assets/{id}/refs` */
  path: string;
  /** The list it is in: `shot:<id>`, `series:<id>`, `asset:<id>`. */
  owner: string;
}

/** 加一张 / 删一张 of a picture set: each is a new version, adopted at once. */
export function usePictureSet({ path, owner }: SetEndpoint) {
  const client = useQueryClient();
  const stored = (product: Product) => {
    client.setQueryData(productKeys.detail(product.id), product);
    void client.invalidateQueries({ queryKey: productKeys.list({ owner }) });
  };
  const add = useMutation({
    mutationFn: ({ file, purpose }: { file: File; purpose?: string }) => {
      const form = new FormData();
      form.append("file", file);
      if (purpose) form.append("purpose", purpose);
      return postForm(path, ProductSchema, form);
    },
    onSuccess: stored,
  });
  const remove = useMutation({
    mutationFn: (idx: number) => del(`${path}/${idx}`, ProductSchema),
    onSuccess: stored,
  });
  return { add, remove };
}

/** The pictures of a set's adopted version, in order. */
export function setPictures(product: Product | undefined): PictureFile[] {
  const v = product?.versions.find((x) => x.id === product.adopted_version_id);
  return (v?.files ?? [])
    .filter((f) => f.role === "ref")
    .map((f, i) => ({ idx: f.idx ?? i, sha256: f.sha256, purpose: f.purpose ?? null }))
    .sort((a, b) => a.idx - b.idx);
}

export interface PictureFile {
  idx: number;
  sha256: string;
  purpose: string | null;
}
