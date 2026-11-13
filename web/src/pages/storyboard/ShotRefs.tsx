import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { fileUrl } from "@/api/client";
import { setPictures } from "@/api/hooks/pictures";
import { useProducts } from "@/api/hooks/products";
import type { Shot } from "@/api/schemas/shots";
import { PictureSet } from "@/components/pictures/PictureSet";
import { paths } from "@/app/paths";

/** `pipeline/pictures.py`: SHOT_REFS, STYLE_BOARD. */
const SHOT_REF_PURPOSES = ["composition", "pose", "light", "style"] as const;
const SHOT_REFS_MAX = 4;

/**
 * 参考 (草图 S4), after the assets: this shot's own reference pictures, each saying what it is
 * for, and the series' 风格板 (managed on the output spec page), sent last. A continuous shot
 * draws no keyframe of its own, so it takes none.
 */
export function ShotRefs({ shot, seriesId }: { shot: Shot; seriesId: string }) {
  const { t } = useTranslation("storyboard");
  const { t: te } = useTranslation("enums");
  const owner = `shot:${shot.id}`;
  const shotProducts = useProducts({ owner });
  const seriesProducts = useProducts({ owner: `series:${seriesId}` });
  const refs = setPictures(shotProducts.data?.find((p) => p.slot === "shot_refs"));
  const board = setPictures(seriesProducts.data?.find((p) => p.slot === "style_board"));

  return (
    <>
      {shot.shot_type === "continuous" ? null : (
        <div className="flex flex-col gap-1.5">
          <div className="text-sm font-medium">
            {t("shot.shotRefs")}{" "}
            <span className="text-xs font-normal text-muted-foreground">
              {t("shot.shotRefsHint")}
            </span>
          </div>
          <PictureSet
            label={t("shot.shotRefs")}
            pictures={refs}
            purposes={SHOT_REF_PURPOSES}
            purposeLabel={(p) => te(`refPurpose.${p}` as "refPurpose.composition")}
            max={SHOT_REFS_MAX}
            path={`/shots/${encodeURIComponent(shot.id)}/refs`}
            owner={owner}
            disabled={shot.confirmed}
          />
        </div>
      )}
      <div className="flex flex-col gap-1.5">
        <div className="text-sm font-medium">
          {t("shot.styleBoard")}{" "}
          <span className="text-xs font-normal text-muted-foreground">
            {t("shot.styleBoardHint")}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {board.map((p) => (
            <img
              key={`${p.idx}-${p.sha256}`}
              src={fileUrl(p.sha256)}
              alt={t("shot.styleBoardPicture", { n: p.idx + 1 })}
              className="size-14 rounded-md bg-media object-cover"
            />
          ))}
          <span className="text-xs text-muted-foreground">
            {board.length
              ? t("shot.styleBoardCount", { count: board.length })
              : t("shot.styleBoardNone")}{" "}
            ·{" "}
            <Link
              to={paths.spec(seriesId)}
              className="text-primary underline-offset-4 hover:underline"
            >
              {t(board.length ? "shot.styleBoardManage" : "shot.styleBoardAdd")}
            </Link>
          </span>
        </div>
      </div>
    </>
  );
}
