import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import type { ProductVersion } from "@/api/schemas/products";
import type { Clip, ClipPatch, Transition } from "@/api/schemas/timeline";
import { SegmentedControl } from "@/components/SegmentedControl";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";

const TRANSITIONS: Transition[] = ["cut", "dissolve", "dip_black"];

/** A volume slider that saves when released; the label follows while dragging. */
function Volume({
  id,
  label,
  value,
  onCommit,
}: {
  id: string;
  label: (n: number) => string;
  value: number;
  onCommit: (n: number) => void;
}) {
  const [drag, setDrag] = useState<number | null>(null);
  const shown = drag ?? value;
  return (
    <div className="flex min-w-40 flex-1 flex-col gap-2">
      <div id={id} className="text-sm">
        {label(shown)}
      </div>
      <Slider
        aria-labelledby={id}
        thumbLabel={label(shown)}
        min={0}
        max={100}
        step={1}
        value={[shown]}
        onValueChange={([n]) => setDrag(n ?? value)}
        onValueCommit={([n]) => {
          setDrag(null);
          if (n !== undefined && n !== value) onCommit(n);
        }}
      />
    </div>
  );
}

/** 片段设置: which take plays, trim the H3 head flash, transition in, dialogue / ambience volume. */
export function ClipSettings({
  clip,
  take,
  modelName,
  generatePath,
  onPatch,
}: {
  clip: Clip;
  take: ProductVersion | undefined;
  modelName: (key: string | null | undefined) => string;
  generatePath: string;
  onPatch: (patch: ClipPatch) => void;
}) {
  const { t } = useTranslation("post");
  const res = typeof take?.payload.resolution === "string" ? take.payload.resolution : "768p";
  return (
    <section
      aria-labelledby="clip-title"
      className="flex min-w-72 flex-1 flex-col gap-4 rounded-xl border bg-card p-4"
    >
      <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
        <h2 id="clip-title" className="text-lg font-bold">
          {t("clip.title", { id: clip.shot_label })}
        </h2>
        <span className="text-sm text-muted-foreground">
          {take
            ? t("clip.src", { n: take.n, model: modelName(take.model_key), res })
            : t("clip.noTake")}
        </span>
        <Link
          to={generatePath}
          className="ml-auto text-sm text-primary underline underline-offset-4"
        >
          {t("clip.switch")}
        </Link>
      </div>
      <label className="flex items-center gap-3">
        <span className="flex flex-1 flex-col gap-0.5">
          <span className="text-sm font-medium">{t("clip.trim")}</span>
          <span className="text-xs text-muted-foreground">{t("clip.trimHint")}</span>
        </span>
        <Switch
          checked={clip.trim_head}
          onCheckedChange={(on) => onPatch({ trim_head: on })}
          aria-label={t("clip.trim")}
        />
      </label>
      <div className="flex flex-col gap-2">
        <div className="text-sm font-medium">{t("clip.transition")}</div>
        <SegmentedControl
          label={t("clip.transition")}
          value={clip.transition}
          onChange={(v) => onPatch({ transition: v })}
          options={TRANSITIONS.map((v) => ({ value: v, label: t(`clip.transitions.${v}`) }))}
          className="w-full"
        />
      </div>
      <div className="flex flex-wrap gap-6">
        <Volume
          key={`d-${clip.id}`}
          id="vol-d"
          label={(n) => t("clip.dialogueVolume", { n })}
          value={clip.dialogue_volume}
          onCommit={(n) => onPatch({ dialogue_volume: n })}
        />
        <Volume
          key={`a-${clip.id}`}
          id="vol-a"
          label={(n) => t("clip.ambienceVolume", { n })}
          value={clip.ambience_volume}
          onCommit={(n) => onPatch({ ambience_volume: n })}
        />
      </div>
    </section>
  );
}
