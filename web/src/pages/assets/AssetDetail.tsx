import { Lock, LockOpen, Upload } from "lucide-react";
import { useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { toast } from "sonner";

import { errorMessage, fileUrl } from "@/api/client";
import { usePatchAsset, useUploadAsset } from "@/api/hooks/assets";
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
import { AssetViews } from "@/pages/assets/AssetViews";
import { ImageCandidates } from "@/pages/assets/Candidates";
import { FinalButton } from "@/pages/assets/FinalButton";
import { isVoiceDraft, STATUS_TONE } from "@/pages/assets/status";
import { VoicePanel } from "@/pages/assets/Voice";

const LETTERS = "ABCD";
// Pictures a reference can be uploaded as (the backend reads their size from the header).
const UPLOAD_TYPES = "image/png,image/jpeg,image/webp";

/** 素材详情: what the asset is, how it is made, its candidates, and lock / unlock. */
export function AssetDetail({
  asset,
  seriesId,
  aspect,
  scriptPath,
  storyboardPath,
  busy,
  onLock,
  onUnlock,
}: {
  asset: Asset;
  seriesId: string;
  aspect: Aspect;
  /** The episode's script page; a scene links to its first line there (`?line=`). */
  scriptPath: string;
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
  const upload = useUploadAsset(seriesId);
  const fileInput = useRef<HTMLInputElement>(null);
  const [intent, setIntent] = useState(asset.intent);
  const [exact, setExact] = useState(asset.text?.exact ?? "");

  const version = product.data ? currentVersion(product.data) : undefined;
  const payload = CandidatesPayloadSchema.safeParse(version?.payload);
  const candidates = payload.success ? payload.data.candidates : [];
  // On-screen text: the version was made with other characters or another method.
  const madeWith = payload.success ? payload.data.text : null;
  const outdated =
    !!asset.text &&
    !!madeWith &&
    (madeWith.exact !== asset.text.exact || madeWith.method !== asset.text.method);
  const srcs = candidates.map((_, i) => {
    const f = version?.files.find((x) => x.role === "candidate" && x.idx === i);
    return f ? fileUrl(f.sha256) : null;
  });
  const locked = asset.status === "locked";
  const pictures = asset.kind !== "voice";
  // A voice's auditions are not a voice yet: its final is what gets locked.
  const needsFinal = asset.kind === "voice" && isVoiceDraft(version);
  const componentId = asset.kind === "text" ? "text" : "img";
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
        <div className="ml-auto flex flex-wrap gap-2">
          {pictures ? (
            <>
              <input
                ref={fileInput}
                type="file"
                accept={UPLOAD_TYPES}
                className="hidden"
                aria-label={t("detail.uploadFile")}
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  e.target.value = "";
                  if (!file) return;
                  upload.mutate(
                    { id: asset.id, file },
                    {
                      onSuccess: () => toast.success(t("detail.uploaded", { name: file.name })),
                      onError: (err) => toast.error(errorMessage(tc, err)),
                    },
                  );
                }}
              />
              <Button
                variant="outline"
                disabled={locked || busy || upload.isPending}
                onClick={() => fileInput.current?.click()}
              >
                <Upload aria-hidden />
                {t("detail.upload")}
              </Button>
            </>
          ) : null}
          <Button
            variant={locked ? "outline" : "default"}
            disabled={busy || !version || (!locked && needsFinal)}
            title={!locked && needsFinal ? t("voice.needsFinal") : undefined}
            onClick={locked ? onUnlock : onLock}
          >
            {locked ? <LockOpen aria-hidden /> : <Lock aria-hidden />}
            {t(locked ? "detail.unlock" : "detail.lock")}
          </Button>
        </div>
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
        {asset.scenes.length ? (
          asset.scenes.map((s) => (
            <Link
              key={s.scene_id}
              to={`${scriptPath}?line=${encodeURIComponent(s.line_ids[0] ?? s.scene_id)}`}
              className="text-primary underline-offset-4 hover:underline"
            >
              {t("detail.scene", { n: s.number })}
            </Link>
          ))
        ) : (
          <span>{asset.note ?? t("detail.noScenes")}</span>
        )}
        {asset.shots.length ? (
          <>
            <span aria-hidden>·</span>
            <span>{t("detail.shots")}</span>
            {asset.shots.map((s) => (
              <Link
                key={s}
                to={storyboardPath}
                className="font-mono text-primary underline-offset-4 hover:underline"
              >
                {s}
              </Link>
            ))}
          </>
        ) : null}
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
                // 声音克隆 comes later (Kelvin 2026-10-20).
                disabled: m === "clone",
                hint: m === "clone" ? t("voice.cloneLater") : undefined,
              }))}
            />
            <p className="text-xs text-muted-foreground">{t(`voice.hint.${asset.voice.method}`)}</p>
          </div>
          {product.data && version ? (
            <VoicePanel
              asset={asset}
              product={product.data}
              version={version}
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
                ? t(
                    (madeWith?.method ?? asset.text.method) === "composite"
                      ? "cands.noteComposite"
                      : "cands.noteText",
                  )
                : asset.kind === "character"
                  ? t("cands.noteCharacter")
                  : t("cands.noteOther")}
            </span>
            {product.data && version ? (
              <span className="ml-auto">
                <FinalButton
                  componentId={componentId}
                  product={product.data}
                  version={version}
                  pick={asset.pick}
                  letter={LETTERS[asset.pick] ?? ""}
                />
              </span>
            ) : null}
          </div>
          {outdated && madeWith ? (
            <p className="text-xs text-tone-warn-fg">
              {t("cands.madeWith", {
                method: t(`text.methods.${madeWith.method}`),
                text: madeWith.exact,
              })}
            </p>
          ) : null}
          {version && candidates.length ? (
            <ImageCandidates
              asset={asset}
              versionNo={version.n}
              candidates={candidates}
              srcs={srcs}
              aspect={aspect}
              madeWith={madeWith}
              locked={locked}
              onPick={(pick) => save({ pick })}
            />
          ) : (
            <EmptyState title={t("cands.emptyImage")} />
          )}
        </div>
      )}

      {asset.kind === "character" ? <AssetViews asset={asset} aspect={aspect} /> : null}
    </section>
  );
}
