import { useTranslation } from "react-i18next";

import { setPictures } from "@/api/hooks/pictures";
import { useProducts } from "@/api/hooks/products";
import { MORE_REF_PURPOSES, MORE_REFS_MAX, type Asset } from "@/api/schemas/assets";
import { PictureSet } from "@/components/pictures/PictureSet";

/** 更多参考图 (草图 A3): the user's own pictures of a character, scene or prop beyond its main
 * one, each with what it is for. Keyframes send them after the main pictures, and only once the
 * main one is locked; they can be added and removed while it is locked (`assets/refs.py`). */
export function MoreRefs({ asset }: { asset: Asset }) {
  const { t } = useTranslation("assets");
  const { t: te } = useTranslation("enums");
  const owner = `asset:${asset.id}`;
  const owned = useProducts({ owner });
  const pictures = setPictures(owned.data?.find((p) => p.slot === "ref_more"));

  return (
    <section aria-label={t("more.title")} className="flex flex-col gap-2">
      <div className="flex flex-wrap items-baseline gap-x-3">
        <h3 className="text-sm font-bold">{t("more.title")}</h3>
        <span className="text-xs text-muted-foreground">
          {asset.status === "locked" ? t("more.hint") : t("more.hintUnlocked")}
        </span>
      </div>
      <PictureSet
        label={t("more.title")}
        pictures={pictures}
        purposes={MORE_REF_PURPOSES}
        purposeLabel={(p) => te(`refPurpose.${p}` as "refPurpose.face")}
        max={MORE_REFS_MAX}
        path={`/assets/${encodeURIComponent(asset.id)}/refs`}
        owner={owner}
        addLabel={t("more.add")}
      />
    </section>
  );
}
