/**
 * 图片来源与编辑 (M5.5): a picture of the user's own as a shot's keyframe, and 以这张为底重画 /
 * 局部修复 / 放大 of any picture of a keyframe, a reference picture or a views set. Each makes a
 * new version of the same product (history keeps the old one).
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { post, postForm } from "@/api/client";
import { productKeys } from "@/api/hooks/products";
import { shotKeys } from "@/api/hooks/shots";
import { JobSchema, type Job } from "@/api/schemas/jobs";
import { ProductSchema } from "@/api/schemas/products";
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
