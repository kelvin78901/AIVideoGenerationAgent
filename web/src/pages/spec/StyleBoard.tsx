import { useTranslation } from "react-i18next";

import { setPictures } from "@/api/hooks/pictures";
import { useProducts } from "@/api/hooks/products";
import { PictureSet } from "@/components/pictures/PictureSet";

/** `pipeline/pictures.py`: STYLE_BOARD. */
const STYLE_BOARD_MAX = 4;

/**
 * 风格板 (M5.5, Kelvin 2026-11-10: on this page, with the series' other settings): up to four
 * pictures of the look the whole series shares; every keyframe sends them last, only for colour,
 * texture and light. Changing it marks keyframes that used it 「待更新」.
 */
export function StyleBoard({ seriesId }: { seriesId: string }) {
  const { t } = useTranslation("spec");
  const owner = `series:${seriesId}`;
  const products = useProducts({ owner });
  const board = setPictures(products.data?.find((p) => p.slot === "style_board"));
  return (
    <PictureSet
      label={t("styleBoard.title")}
      pictures={board}
      purposes={["style"]}
      purposeLabel={() => t("styleBoard.title")}
      max={STYLE_BOARD_MAX}
      path={`/series/${encodeURIComponent(seriesId)}/style-board`}
      owner={owner}
      addLabel={t("styleBoard.add")}
    />
  );
}
