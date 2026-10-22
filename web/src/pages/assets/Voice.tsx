import { Sparkles } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { errorMessage, fileUrl } from "@/api/client";
import { useComponentModels, useResolvedConfig } from "@/api/hooks/config";
import { useRunProduct } from "@/api/hooks/products";
import { CandidatesPayloadSchema, VoiceFinalSchema, type Asset } from "@/api/schemas/assets";
import type { Product, ProductVersion, VersionFile } from "@/api/schemas/products";
import { AudioPlayer } from "@/components/AudioPlayer";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { isVoiceDraft } from "@/pages/assets/status";

const LETTERS = "ABC";

function clip(f: VersionFile | undefined, label: string) {
  return f ? (
    <AudioPlayer
      src={fileUrl(f.sha256)}
      waveform={f.waveform}
      duration={f.duration_s}
      label={label}
      className="flex-1"
    />
  ) : null;
}

/**
 * 音色: the free auditions to pick from (each reads the character's lines), or the final made
 * from one (the voice's own sample and its emotion variants); then the script lines to try it
 * with. A draft is never locked: 「出终版」 first.
 */
export function VoicePanel({
  asset,
  product,
  version,
  locked,
  onPick,
}: {
  asset: Asset;
  product: Product;
  version: ProductVersion;
  locked: boolean;
  onPick: (i: number) => void;
}) {
  const { t } = useTranslation("assets");
  const { t: te } = useTranslation("enums");
  const draft = isVoiceDraft(version);
  const cands = CandidatesPayloadSchema.safeParse(version.payload);
  const candidates = draft && cands.success ? cands.data.candidates : [];
  const final = VoiceFinalSchema.safeParse(version.payload);
  const own = (i: number) => version.files.filter((f) => f.role === "candidate" && f.idx === i);
  const anchors = version.files.filter((f) => f.role === "anchor");
  // A line is tried with the picked audition, or the final's sample.
  const tryWith = draft ? own(asset.pick) : anchors;

  return (
    <div className="flex flex-col gap-3">
      {draft ? (
        <>
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className="text-xs text-muted-foreground">{t("voice.note")}</span>
            {!locked ? (
              <span className="ml-auto">
                <VoiceFinalButton
                  asset={asset}
                  product={product}
                  version={version}
                  letter={LETTERS[asset.pick] ?? ""}
                />
              </span>
            ) : null}
          </div>
          <div role="radiogroup" aria-label={t("voice.cands")} className="flex flex-col gap-2">
            {candidates.map((c, i) => {
              const on = asset.pick === i;
              const label = t("voice.label", {
                n: version.n,
                letter: LETTERS[i] ?? "",
                label: c.label ?? "",
              });
              return (
                <div
                  key={i}
                  className={cn(
                    "flex flex-wrap items-center gap-3 rounded-lg border px-3 py-2",
                    on && "border-primary bg-tone-info-bg/40",
                  )}
                >
                  <span className="w-40 shrink-0 text-sm">{label}</span>
                  {clip(own(i)[0], label)}
                  <Button
                    size="sm"
                    role="radio"
                    aria-checked={on}
                    variant={on ? "default" : "outline"}
                    disabled={locked}
                    onClick={() => onPick(i)}
                  >
                    {t(on ? "voice.picked" : "voice.pick")}
                  </Button>
                </div>
              );
            })}
          </div>
        </>
      ) : final.success ? (
        <section aria-label={t("voice.finalTitle")} className="flex flex-col gap-2">
          <div className="text-sm font-medium">
            {t("voice.final", {
              label: final.data.label ?? "",
              provider: t(`voice.provider.${final.data.provider === "local" ? "local" : "api"}`),
            })}
          </div>
          <div className="flex items-center gap-3">
            <span className="w-24 shrink-0 text-xs text-muted-foreground">{t("voice.anchor")}</span>
            {clip(anchors[0], t("voice.anchor"))}
          </div>
          <div className="text-xs font-medium">{t("voice.variants")}</div>
          <ul aria-label={t("voice.variants")} className="grid gap-2 sm:grid-cols-2">
            {version.files
              .filter((f) => f.role === "variant")
              .map((f) => {
                const name = te(`emotion.${f.emotion ?? "calm"}` as "emotion.calm");
                return (
                  <li key={f.sha256} className="flex items-center gap-2">
                    <span className="w-12 shrink-0 text-xs">{name}</span>
                    {clip(f, name)}
                  </li>
                );
              })}
          </ul>
          <p className="text-xs text-muted-foreground">{t("voice.variantsHint")}</p>
        </section>
      ) : null}
      {asset.voice?.lines.length ? (
        <div className="flex flex-col gap-1.5">
          <div className="text-xs font-medium">{t("voice.lines")}</div>
          {asset.voice.lines.map((l, j) => (
            <div key={l.text} className="flex flex-wrap items-center gap-2 text-sm">
              <span>{l.text}</span>
              <span className="text-xs text-muted-foreground">{l.tone}</span>
              {clip(tryWith.find((f) => f.line === j) ?? tryWith[0], l.text)}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

/**
 * 「出终版」 from the picked audition: on the route's API model (a MiniMax design and its five
 * emotions; it costs over the per-call cap, so it waits for a yes), or locally for a voice whose
 * source is 本地 TTS (free).
 */
function VoiceFinalButton({
  asset,
  product,
  version,
  letter,
}: {
  asset: Asset;
  product: Product;
  version: ProductVersion;
  letter: string;
}) {
  const { t } = useTranslation("assets");
  const { t: tc } = useTranslation();
  const config = useResolvedConfig("voice").data?.values;
  const models = useComponentModels("voice");
  const run = useRunProduct(product.id);
  const local = asset.voice?.method === "local";
  const apiModel = config?.api_model ?? null;
  if (!local && !apiModel) return null;
  const model = models.find((m) => m.key === apiModel);
  const busy = run.isPending || product.running !== null;
  return (
    <Button
      size="sm"
      variant="outline"
      disabled={busy}
      onClick={() =>
        run.mutate(
          {
            mode: "run",
            where: local ? "local" : "api",
            params: { source_version_id: version.id, source_idx: asset.pick },
          },
          {
            onSuccess: () => toast.info(t("voice.finalStarted", { letter })),
            onError: (err) => toast.error(errorMessage(tc, err)),
          },
        )
      }
    >
      <Sparkles aria-hidden />
      {local
        ? t("voice.finalLocal")
        : t("voice.finalApi", { model: model?.display ?? apiModel ?? "" })}
    </Button>
  );
}
