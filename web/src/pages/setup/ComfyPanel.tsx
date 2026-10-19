/**
 * 你的 ComfyUI (SPEC 6.4.1): what the last scan identified, read-only, and the ComfyUI-Manager
 * snapshots with one-click rollback. A rollback takes effect when the user restarts ComfyUI; we
 * never restart it ourselves.
 */
import { ChevronDown, History, RotateCcw } from "lucide-react";
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { ApiError, errorMessage } from "@/api/client";
import { useComfySnapshots, useRestoreSnapshot, useTakeSnapshot } from "@/api/hooks/comfy";
import type { ComfyEnv, ComfyScan, ComfySnapshot } from "@/api/schemas/comfy";
import type { Message } from "@/api/schemas/common";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogTitle,
} from "@/components/ui/dialog";
import { formatBytes, formatDateTime } from "@/lib/format";

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="min-w-0 truncate text-[13px]">{children}</dd>
    </div>
  );
}

/** Manager's own failures (`comfy_snapshot_failed`) read better with their reason spelled out. */
function useSnapshotError() {
  const { t } = useTranslation("setup");
  const { t: tc } = useTranslation();
  return (err: unknown) => {
    const reason = err instanceof ApiError ? err.params.reason : undefined;
    if (
      err instanceof ApiError &&
      err.code === "comfy_snapshot_failed" &&
      typeof reason === "string"
    )
      return t(`snapshotError.${reason}` as "snapshotError.failed", {
        defaultValue: errorMessage(tc, err),
      });
    return errorMessage(tc, err);
  };
}

function Details({ scan, env }: { scan: ComfyScan; env: ComfyEnv | null }) {
  const { t } = useTranslation("setup");
  const [open, setOpen] = useState(false);
  const packs = env?.node_packs ?? [];
  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger asChild>
        <Button variant="ghost" size="sm" className="-ml-2 text-primary">
          {t("comfy.details", { packs: packs.length, models: scan.models.length })}
          <ChevronDown className={open ? "rotate-180" : undefined} aria-hidden />
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent className="grid gap-3 pt-2 md:grid-cols-2">
        <table className="w-full text-[13px]" aria-label={t("comfy.packs")}>
          <thead className="text-left text-xs text-muted-foreground">
            <tr>
              <th className="py-1 pr-3 font-medium">{t("comfy.packs")}</th>
              <th className="py-1 pr-3 font-medium">{t("comfy.col.source")}</th>
              <th className="py-1 font-medium">{t("comfy.col.version")}</th>
            </tr>
          </thead>
          <tbody>
            {packs.map((p) => (
              <tr key={p.name} className="border-t border-border/60">
                <td className="py-1 pr-3 font-medium break-all">{p.name}</td>
                <td className="py-1 pr-3 text-muted-foreground">{t(`comfy.source.${p.source}`)}</td>
                <td className="py-1 font-mono text-xs" title={p.commit ?? undefined}>
                  {p.version ?? (p.commit ? p.commit.slice(0, 7) : t("none"))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <table className="w-full text-[13px]" aria-label={t("comfy.models")}>
          <thead className="text-left text-xs text-muted-foreground">
            <tr>
              <th className="py-1 pr-3 font-medium">{t("comfy.models")}</th>
              <th className="py-1 pr-3 font-medium">{t("comfy.col.folder")}</th>
              <th className="py-1 text-right font-medium">{t("comfy.col.size")}</th>
            </tr>
          </thead>
          <tbody>
            {scan.models.map((m) => (
              <tr key={`${m.folder}/${m.name}`} className="border-t border-border/60">
                <td className="py-1 pr-3 break-all" title={m.path ?? undefined}>
                  {m.name}
                </td>
                <td className="py-1 pr-3 text-muted-foreground">{m.folder}</td>
                <td className="py-1 text-right font-mono text-xs">
                  {m.size_bytes != null ? formatBytes(m.size_bytes) : t("none")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {scan.models_truncated ? (
          <p className="text-xs text-muted-foreground md:col-span-2">{t("comfy.truncated")}</p>
        ) : null}
      </CollapsibleContent>
    </Collapsible>
  );
}

function SnapshotRow({
  snap,
  itemName,
  busy,
  onRestore,
}: {
  snap: ComfySnapshot;
  itemName: (id: string) => string;
  busy: boolean;
  onRestore: (snap: ComfySnapshot) => void;
}) {
  const { t } = useTranslation("setup");
  const time = formatDateTime(snap.created_at);
  const items = snap.changes.map((m) => itemName(String(m.params.item)));
  return (
    <li
      aria-label={t("snapshots.rowLabel", { time })}
      className="flex flex-wrap items-center gap-x-3 gap-y-1.5 border-t border-border/60 py-2.5 first:border-t-0"
    >
      <span className="font-mono text-[13px]">{time}</span>
      <StatusBadge tone={snap.reason === "install" ? "info" : "neutral"} icon={null}>
        {t(`snapshots.reason.${snap.reason}`)}
      </StatusBadge>
      <span className="min-w-0 flex-1 truncate text-[13px] text-muted-foreground">
        {items.length
          ? t("snapshots.for", { items: items.join(t("snapshots.sep")) })
          : snap.manager_name}
      </span>
      {snap.restored_at ? (
        <StatusBadge tone="warn" icon={null}>
          {t("snapshots.restored")}
        </StatusBadge>
      ) : null}
      <Button
        size="sm"
        variant="outline"
        disabled={busy}
        onClick={() => onRestore(snap)}
        aria-label={t("snapshots.restoreLabel", { time })}
      >
        <RotateCcw aria-hidden />
        {t("snapshots.restore")}
      </Button>
    </li>
  );
}

export function ComfyPanel({
  scan,
  env,
  installing,
  snapshotError,
  itemName,
}: {
  scan: ComfyScan;
  env: ComfyEnv | null;
  /** Rollback waits while an install runs. */
  installing: boolean;
  /** Why the last install could not take its snapshot (`setup:error.snapshot_*`). */
  snapshotError: Message | null;
  itemName: (id: string) => string;
}) {
  const { t } = useTranslation("setup");
  const snapshots = useComfySnapshots();
  const take = useTakeSnapshot();
  const restore = useRestoreSnapshot();
  const snapshotErrorText = useSnapshotError();
  const [asked, setAsked] = useState<ComfySnapshot | null>(null);
  const none = t("none");
  const version = (v: string | null | undefined) => v ?? none;

  const doRestore = (snap: ComfySnapshot) =>
    restore.mutate(snap.id, {
      onSuccess: () => {
        setAsked(null);
        toast.success(t("snapshots.restartToast"));
      },
      onError: (err) => toast.error(snapshotErrorText(err)),
    });

  return (
    <section
      aria-labelledby="comfy-title"
      className="flex flex-col gap-3.5 rounded-xl border bg-card p-4.5"
    >
      <div className="flex flex-wrap items-baseline gap-2.5">
        <h2 id="comfy-title" className="text-[17px] font-bold">
          {t("comfy.title")}
        </h2>
        <span className="text-xs text-muted-foreground">{t("comfy.hint")}</span>
      </div>
      <dl className="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-x-5 gap-y-2.5">
        <Fact label={t("comfy.where")}>
          <span className="font-mono text-xs" title={scan.root ?? undefined}>
            {scan.root ?? none}
          </span>{" "}
          <span className="text-muted-foreground">· {t(`comfy.kind.${scan.kind}`)}</span>
        </Fact>
        <Fact label={t("comfy.url")}>
          {scan.url ? <span className="font-mono text-xs">{scan.url}</span> : t("comfy.notRunning")}
        </Fact>
        <Fact label={t("comfy.version")}>
          {t("comfy.versionValue", {
            comfy: version(env?.comfyui_version),
            python: version(env?.python),
            torch: version(env?.torch),
          })}
        </Fact>
        <Fact label={t("comfy.manager")}>
          {scan.manager ? version(scan.manager.version) : t("comfy.noManager")}
        </Fact>
      </dl>
      <Details scan={scan} env={env} />

      {snapshotError ? (
        <p
          role="alert"
          className="rounded-lg bg-tone-warn-bg px-3 py-2 text-[13px] text-tone-warn-fg"
        >
          {t(`error.${snapshotError.code}` as "error.snapshot_failed", {
            ...snapshotError.params,
            defaultValue: snapshotError.code,
          })}
        </p>
      ) : null}

      <div className="flex flex-col gap-1 rounded-lg border px-3.5 py-2.5">
        <div className="flex flex-wrap items-center gap-2.5">
          <History className="size-4 text-muted-foreground" aria-hidden />
          <h3 className="text-sm font-bold">{t("snapshots.title")}</h3>
          <span className="text-xs text-muted-foreground">{t("snapshots.hint")}</span>
          <Button
            size="sm"
            variant="outline"
            className="ml-auto"
            disabled={take.isPending || installing}
            onClick={() =>
              take.mutate(undefined, {
                onSuccess: (snap) =>
                  toast.success(t("snapshots.taken", { name: snap.manager_name })),
                onError: (err) => toast.error(snapshotErrorText(err)),
              })
            }
          >
            {t("snapshots.take")}
          </Button>
        </div>
        {snapshots.data?.length ? (
          <ul aria-label={t("snapshots.title")}>
            {snapshots.data.map((s) => (
              <SnapshotRow
                key={s.id}
                snap={s}
                itemName={itemName}
                busy={installing || restore.isPending}
                onRestore={setAsked}
              />
            ))}
          </ul>
        ) : snapshots.isSuccess ? (
          <p className="py-1.5 text-[13px] text-muted-foreground">{t("snapshots.empty")}</p>
        ) : null}
      </div>

      {asked ? (
        <Dialog open onOpenChange={(open) => (!open ? setAsked(null) : undefined)}>
          <DialogContent role="alertdialog" className="gap-3">
            <DialogTitle className="text-base font-bold">
              {t("snapshots.confirmTitle", { time: formatDateTime(asked.created_at) })}
            </DialogTitle>
            <DialogDescription className="text-sm leading-relaxed text-foreground">
              {t("snapshots.confirmBody")}
            </DialogDescription>
            <DialogFooter>
              <Button variant="outline" disabled={restore.isPending} onClick={() => setAsked(null)}>
                {t("snapshots.cancel")}
              </Button>
              <Button disabled={restore.isPending} onClick={() => doRestore(asked)}>
                {t("snapshots.confirmOk")}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      ) : null}
    </section>
  );
}
