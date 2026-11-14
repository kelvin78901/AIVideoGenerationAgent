import { Sparkles, Upload } from "lucide-react";
import { useId, useRef } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { errorMessage, fileUrl } from "@/api/client";
import { useUploadVoiceSample } from "@/api/hooks/assets";
import { useRunProduct } from "@/api/hooks/products";
import type { Asset } from "@/api/schemas/assets";
import type { Product } from "@/api/schemas/products";
import { AudioPlayer } from "@/components/AudioPlayer";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/form";
import { formatCost } from "@/lib/format";

const SAMPLE_TYPES = "audio/wav,audio/x-wav,audio/mpeg,audio/mp4,audio/x-m4a,.wav,.mp3,.m4a";

/**
 * 声音克隆 (M5.5 sketch A5): the sample, 「我确认已获得声音本人的授权」, then a clone. There are
 * no auditions: 「克隆」 makes the final on the route's API model (MiniMax: the clone fee and
 * five emotions), 本地 makes it with IndexTTS reading in the sample's voice, free. Both stay
 * greyed out until there is a sample and the box is ticked; a new sample unticks it.
 */
export function VoiceClone({
  asset,
  product,
  locked,
  onConsent,
}: {
  asset: Asset;
  product: Product;
  locked: boolean;
  onConsent: (consent: boolean) => void;
}) {
  const { t } = useTranslation("assets");
  const { t: tc } = useTranslation();
  const upload = useUploadVoiceSample(asset.series_id);
  const run = useRunProduct(product.id);
  const fileInput = useRef<HTMLInputElement>(null);
  const consentId = useId();
  const sample = asset.voice?.sample ?? null;
  const consent = asset.voice?.consent ?? false;
  const cost = product.estimate?.final_usd ?? null;
  const busy = run.isPending || product.running !== null;
  const blocked = !sample
    ? t("voice.clone.needSample")
    : !consent
      ? t("voice.clone.needConsent")
      : null;

  const start = (where: "api" | "local") =>
    run.mutate(
      { mode: "run", where },
      {
        onSuccess: () => toast.info(t("voice.clone.started")),
        onError: (err) => toast.error(errorMessage(tc, err)),
      },
    );

  return (
    <section
      aria-label={t("voice.clone.title")}
      className="flex flex-col gap-3 rounded-lg border px-3 py-3"
    >
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-sm font-medium">{t("voice.clone.title")}</span>
        <input
          ref={fileInput}
          type="file"
          accept={SAMPLE_TYPES}
          className="hidden"
          aria-label={t("voice.clone.upload")}
          onChange={(e) => {
            const file = e.target.files?.[0];
            e.target.value = "";
            if (!file) return;
            upload.mutate(
              { id: asset.id, file },
              { onError: (err) => toast.error(errorMessage(tc, err)) },
            );
          }}
        />
        <Button
          size="sm"
          variant="outline"
          disabled={locked || upload.isPending}
          onClick={() => fileInput.current?.click()}
        >
          <Upload aria-hidden />
          {t(sample ? "voice.clone.replace" : "voice.clone.upload")}
        </Button>
        <span className="text-xs text-muted-foreground">{t("voice.clone.formats")}</span>
      </div>
      {sample ? (
        <div className="flex flex-wrap items-center gap-3">
          <span className="w-56 shrink-0 truncate text-sm">
            {t("voice.clone.sample", {
              name: sample.name,
              seconds: sample.duration_s.toFixed(1),
            })}
          </span>
          <AudioPlayer
            src={fileUrl(sample.sha256)}
            waveform={sample.waveform}
            duration={sample.clip_s}
            label={sample.name}
            className="flex-1"
          />
        </div>
      ) : null}
      <div className="flex items-start gap-2">
        <Checkbox
          id={consentId}
          checked={consent}
          disabled={locked || !sample}
          onCheckedChange={(v) => onConsent(v === true)}
          className="mt-0.5"
        />
        <div className="flex flex-col gap-0.5">
          <Label htmlFor={consentId} className="leading-snug font-normal">
            {t("voice.clone.consent")}
          </Label>
          <span className="text-xs text-muted-foreground">{t("voice.clone.consentHint")}</span>
        </div>
      </div>
      {!locked ? (
        <div className="flex flex-wrap items-center justify-end gap-2">
          {blocked ? <span className="text-xs text-muted-foreground">{blocked}</span> : null}
          <Button
            size="sm"
            variant="outline"
            disabled={busy || blocked !== null}
            onClick={() => start("local")}
          >
            {t("voice.finalLocal")}
          </Button>
          <Button size="sm" disabled={busy || blocked !== null} onClick={() => start("api")}>
            <Sparkles aria-hidden />
            {cost !== null
              ? t("voice.clone.run", { cost: formatCost(cost) })
              : t("voice.clone.runFree")}
          </Button>
        </div>
      ) : null}
      <p className="text-xs text-muted-foreground">{t("voice.clone.local")}</p>
    </section>
  );
}
