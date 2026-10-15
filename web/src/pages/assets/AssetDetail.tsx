import { Lock, LockOpen } from "lucide-react";
import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { toast } from "sonner";

import { errorMessage } from "@/api/client";
import { usePatchAsset } from "@/api/hooks/assets";
import { useProduct } from "@/api/hooks/products";
import {
  CandidatesPayloadSchema,
  TextMethodSchema,
  TextStyleSchema,
  VoiceMethodSchema,
  type Asset,
  type AssetPatch,
} from "@/api/schemas/assets";
import type { Aspect } from "@/api/schemas/spec";
import { Chip } from "@/components/Chip";
import { EmptyState } from "@/components/EmptyState";
import { SegmentedControl } from "@/components/SegmentedControl";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Input, Label, Textarea } from "@/components/ui/form";
import { currentVersion } from "@/lib/versions";
import { STATUS_TONE } from "@/pages/assets/status";
import { ImageCandidates, VoiceCandidates } from "@/pages/assets/Candidates";

/** 素材详情: what the asset is, how it is made, its candidates, and lock / unlock. */
export function AssetDetail({
  asset,
  seriesId,
  aspect,
  storyboardPath,
  busy,
  onLock,
  onUnlock,
}: {
  asset: Asset;
  seriesId: string;
  aspect: Aspect;
  storyboardPath: string;
  busy: boolean;
  onLock: () => void;
  onUnlock: () => void;
}) {
  const { t } = useTranslation("assets");
  const { t: te } = useTranslation("enums");
  const { t: tc } = useTranslation();
  const { t: tcomp } = useTranslation("components");
  const ids = useId();
  const product = useProduct(asset.product_id);
  const patchAsset = usePatchAsset(seriesId);
  const [intent, setIntent] = useState(asset.intent);
  const [exact, setExact] = useState(asset.text?.exact ?? "");

  const version = product.data ? currentVersion(product.data) : undefined;
  const payload = CandidatesPayloadSchema.safeParse(version?.payload);
  const candidates = payload.success ? payload.data.candidates : [];
  const locked = asset.status === "locked";
  const save = (p: AssetPatch, done?: string) =>
    patchAsset.mutate(
      { id: asset.id, patch: p },
      {
        onSuccess: () => {
          if (done) toast.success(done);
        },
        onError: (err) => toast.error(errorMessage(tc, err)),
      },
    );

  return (
    <section
      aria-labelledby={`${ids}-name`}
      className="flex flex-col gap-4 rounded-lg border bg-card p-4"
    >
      <div className="flex flex-wrap items-center gap-2">
        <h2 id={`${ids}-name`} className="text-lg font-bold">
          {asset.name}
        </h2>
        <StatusBadge icon={null}>{te(`assetKind.${asset.kind}`)}</StatusBadge>
        <StatusBadge tone={STATUS_TONE[asset.status]} icon={null}>
          {te(`assetStatus.${asset.status}`)}
        </StatusBadge>
        <Button
          className="ml-auto"
          variant={locked ? "outline" : "default"}
          disabled={busy || !version}
          onClick={locked ? onUnlock : onLock}
        >
          {locked ? <LockOpen aria-hidden /> : <Lock aria-hidden />}
          {t(locked ? "detail.unlock" : "detail.lock")}
        </Button>
      </div>

      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
        <span>
          {t("detail.source", {
            source: tcomp(`asset.source.${asset.source.code}` as "asset.source.episode", {
              ...asset.source.params,
              defaultValue: asset.source.code,
            }),
          })}
        </span>
        <span aria-hidden>·</span>
        <span>{t("detail.appears")}</span>
        {asset.shots.length ? (
          asset.shots.map((s) => (
            <Link
              key={s}
              to={storyboardPath}
              className="font-mono text-primary underline-offset-4 hover:underline"
            >
              {s}
            </Link>
          ))
        ) : (
          <span>{t("detail.noShots")}</span>
        )}
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor={`${ids}-desc`}>{t("detail.desc")}</Label>
        <Textarea
          id={`${ids}-desc`}
          rows={3}
          value={intent}
          onChange={(e) => setIntent(e.target.value)}
          onBlur={() => {
            if (intent !== asset.intent) save({ intent }, t("detail.descSaved"));
          }}
        />
        <p className="text-xs text-muted-foreground">{t("detail.descHint")}</p>
      </div>

      {asset.text ? (
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={`${ids}-exact`}>{t("text.exact")}</Label>
            <Input
              id={`${ids}-exact`}
              value={exact}
              onChange={(e) => setExact(e.target.value)}
              onBlur={() => {
                if (exact !== asset.text?.exact) save({ text: { exact } });
              }}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <div className="text-sm font-medium">{t("text.method")}</div>
            <SegmentedControl
              label={t("text.method")}
              value={asset.text.method}
              onChange={(method) => save({ text: { method } })}
              options={TextMethodSchema.options.map((m) => ({
                value: m,
                label: t(`text.methods.${m}`),
              }))}
            />
            <p className="text-xs text-muted-foreground">{t(`text.hint.${asset.text.method}`)}</p>
          </div>
          <div
            className="flex flex-wrap items-center gap-1.5"
            role="radiogroup"
            aria-label={t("text.style")}
          >
            <span className="mr-1 text-sm font-medium">{t("text.style")}</span>
            {TextStyleSchema.options.map((s) => (
              <Chip
                key={s}
                role="radio"
                selected={asset.text?.style === s}
                onClick={() => save({ text: { style: s } })}
              >
                {t(`text.styles.${s}`)}
              </Chip>
            ))}
          </div>
        </div>
      ) : null}

      {asset.voice ? (
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <div className="text-sm font-medium">{t("voice.source")}</div>
            <SegmentedControl
              label={t("voice.source")}
              value={asset.voice.method}
              onChange={(method) => save({ voice: { method } })}
              options={VoiceMethodSchema.options.map((m) => ({
                value: m,
                label: t(`voice.methods.${m}`),
              }))}
            />
            <p className="text-xs text-muted-foreground">{t(`voice.hint.${asset.voice.method}`)}</p>
          </div>
          {version && candidates.length ? (
            <VoiceCandidates
              asset={asset}
              versionNo={version.n}
              candidates={candidates}
              locked={locked}
              onPick={(pick) => save({ pick })}
            />
          ) : (
            <EmptyState title={t("cands.emptyVoice")} />
          )}
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-baseline gap-x-3">
            <h3 className="text-sm font-bold">{t("cands.title")}</h3>
            <span className="text-xs text-muted-foreground">
              {asset.text
                ? t("cands.noteText")
                : asset.kind === "character"
                  ? t("cands.noteCharacter")
                  : t("cands.noteOther")}
            </span>
          </div>
          {version && candidates.length ? (
            <ImageCandidates
              asset={asset}
              versionNo={version.n}
              candidates={candidates}
              aspect={aspect}
              locked={locked}
              onPick={(pick) => save({ pick })}
            />
          ) : (
            <EmptyState title={t("cands.emptyImage")} />
          )}
        </div>
      )}
    </section>
  );
}
