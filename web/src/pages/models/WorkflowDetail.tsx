/**
 * One workflow, opened below its row: where it comes from, its tier, and three tabs — bindings
 * (slot ↔ node title and field, guesses to confirm), health check (missing node packs and models,
 * installed after the ComfyUI change list), trial (sample inputs, result, then 我的工作流).
 */
import { Loader2 } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { errorMessage } from "@/api/client";
import { useComfyEnv } from "@/api/hooks/comfy";
import {
  useCheckWorkflow,
  useDepsPlan,
  useInstallDeps,
  useSaveBindings,
  useSetWorkflowTier,
  useTrialWorkflow,
} from "@/api/hooks/workflows";
import type { Message } from "@/api/schemas/common";
import type { Binding, Workflow } from "@/api/schemas/workflows";
import { MediaThumb } from "@/components/MediaThumb";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { formatBytes, formatDateTime } from "@/lib/format";
import type { Tone } from "@/lib/tone";
import { pendingCount } from "@/pages/models/workflowStatus";
import { ConfirmInstall } from "@/pages/setup/ConfirmInstall";

const stateTone: Record<Binding["state"], Tone> = {
  dramastudio: "info",
  confirmed: "pass",
  guessed: "warn",
};

const SELECT =
  "h-8 w-full min-w-0 rounded-md border bg-card px-2 text-[13px] outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60";

function useOnError() {
  const { t } = useTranslation();
  return (err: unknown) => toast.error(errorMessage(t, err));
}

function useSlotName() {
  const { t } = useTranslation("workflows");
  return (b: Binding) => t(`slot.${b.slot}`, { n: b.index ?? 1 });
}

function Header({ w }: { w: Workflow }) {
  const { t } = useTranslation("workflows");
  const setTier = useSetWorkflowTier(w.id);
  const onError = useOnError();
  const pending = pendingCount(w);
  const passed = w.trial?.status === "passed" && !w.file_changed;
  const blocked = pending ? t("promoteBlocked.pending") : passed ? null : t("promoteBlocked.trial");
  const caps = [
    t("caps.aspects", { list: w.caps.aspects.join(" ") }),
    w.caps.max_seconds ? t("caps.maxSeconds", { n: w.caps.max_seconds }) : null,
    w.caps.refs ? t("caps.refs", { n: w.caps.refs }) : null,
    w.caps.vram_gb ? t("caps.vram", { n: w.caps.vram_gb }) : null,
  ].filter(Boolean);
  const change = (tier: "mine" | "unverified") =>
    setTier.mutate(tier, {
      onSuccess: () => toast.success(t(tier === "mine" ? "promoted" : "demoted", { name: w.name })),
      onError,
    });

  return (
    <div className="flex flex-wrap items-start gap-x-6 gap-y-2">
      <div className="flex min-w-0 flex-[1_1_420px] flex-col gap-1 text-[13px]">
        <span className="text-muted-foreground">
          {t(`source.${w.source}`, { slug: w.slug, origin: w.origin ?? "" })}
          {" · "}
          <span className="font-mono text-xs" title={w.file_sha256}>
            sha256 {w.file_sha256.slice(0, 12)}…
          </span>
        </span>
        <span>{t("caps.line", { list: caps.join(" · ") })}</span>
        <span className="text-xs leading-relaxed text-muted-foreground">
          {t(`tierWhy.${w.tier}`)}
        </span>
      </div>
      {w.source === "user" ? (
        <div className="flex flex-col items-end gap-1">
          {w.tier === "mine" ? (
            <Button
              variant="outline"
              size="sm"
              disabled={setTier.isPending}
              onClick={() => change("unverified")}
            >
              {t("demote")}
            </Button>
          ) : (
            <Button
              size="sm"
              disabled={!!blocked || setTier.isPending}
              onClick={() => change("mine")}
            >
              {t("promote")}
            </Button>
          )}
          {w.tier !== "mine" && blocked ? (
            <span className="text-xs text-muted-foreground">{blocked}</span>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function Bindings({ w }: { w: Workflow }) {
  const { t } = useTranslation("workflows");
  const slotName = useSlotName();
  const save = useSaveBindings(w.id);
  const onError = useOnError();
  const [draft, setDraft] = useState<Binding[] | null>(null);
  const rows = draft ?? w.bindings;
  const pending = rows.filter((b) => b.state === "guessed").length;
  const nodes = w.nodes;
  const edit = (i: number, patch: Partial<Binding>) =>
    setDraft(rows.map((b, j) => (j === i ? { ...b, ...patch } : b)));

  return (
    <div className="flex flex-col gap-2.5">
      <p className="text-[13px] leading-relaxed text-muted-foreground">
        {w.uses_dramastudio_nodes ? t("bindings.dramastudio") : t("bindings.lead")}
      </p>
      {pending ? (
        <p className="rounded-md bg-tone-warn-bg px-3 py-2 text-[13px] text-tone-warn-fg">
          {t("bindings.pendingNote", { count: pending })}
        </p>
      ) : null}
      <div className="overflow-x-auto rounded-lg border bg-card">
        <table className="w-full min-w-[720px] text-[13px]" aria-label={t("tab.bindings")}>
          <thead className="bg-muted/50 text-left text-xs text-muted-foreground">
            <tr>
              {(["slot", "node", "class", "field", "state"] as const).map((c) => (
                <th key={c} className="px-3 py-1.5 font-medium whitespace-nowrap">
                  {t(`bindings.col.${c}`)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((b, i) => {
              const fixed = b.state === "dramastudio";
              const node = nodes.find((n) => n.title === b.node_title);
              const slot = slotName(b);
              return (
                <tr key={`${b.slot}-${b.index ?? 0}`} className="border-t border-border/60">
                  <td className="px-3 py-1.5 font-medium whitespace-nowrap">{slot}</td>
                  <td className="px-3 py-1.5">
                    {fixed ? (
                      b.node_title
                    ) : (
                      <select
                        aria-label={t("bindings.nodeOf", { slot })}
                        className={SELECT}
                        value={b.node_title}
                        onChange={(e) => {
                          const n = nodes.find((x) => x.title === e.target.value);
                          edit(i, {
                            node_title: e.target.value,
                            node_class: n?.class_type ?? b.node_class,
                            field: b.field === null ? null : (n?.fields[0] ?? null),
                          });
                        }}
                      >
                        {nodes.map((n) => (
                          <option key={n.title} value={n.title}>
                            {n.title}
                          </option>
                        ))}
                      </select>
                    )}
                  </td>
                  <td className="px-3 py-1.5 font-mono text-xs text-muted-foreground">
                    {b.node_class}
                  </td>
                  <td className="px-3 py-1.5">
                    {b.field === null ? (
                      <span className="text-muted-foreground">{t("bindings.output")}</span>
                    ) : fixed ? (
                      <span className="font-mono text-xs">{b.field}</span>
                    ) : (
                      <select
                        aria-label={t("bindings.fieldOf", { slot })}
                        className={`${SELECT} font-mono text-xs`}
                        value={b.field}
                        onChange={(e) => edit(i, { field: e.target.value })}
                      >
                        {(node?.fields ?? [b.field]).map((f) => (
                          <option key={f} value={f}>
                            {f}
                          </option>
                        ))}
                      </select>
                    )}
                  </td>
                  <td className="px-3 py-1.5 whitespace-nowrap">
                    <StatusBadge tone={stateTone[b.state]} icon={null}>
                      {t(`bindings.state.${b.state}`)}
                    </StatusBadge>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {!w.uses_dramastudio_nodes && (pending || draft) ? (
        <div className="flex gap-2">
          <Button
            size="sm"
            disabled={save.isPending}
            onClick={() =>
              save.mutate(
                rows.map((b) => ({ ...b, state: "confirmed" as const })),
                {
                  onSuccess: () => {
                    setDraft(null);
                    toast.success(t("bindings.saved"));
                  },
                  onError,
                },
              )
            }
          >
            {t("bindings.save")}
          </Button>
          {draft ? (
            <Button size="sm" variant="ghost" onClick={() => setDraft(null)}>
              {t("bindings.reset")}
            </Button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function Check({ w }: { w: Workflow }) {
  const { t } = useTranslation("workflows");
  const run = useCheckWorkflow(w.id);
  const plan = useDepsPlan(w.id);
  const install = useInstallDeps(w.id);
  const comfy = useComfyEnv();
  const onError = useOnError();
  const [changes, setChanges] = useState<Message[] | null>(null);
  const c = w.check;
  if (!c) return <p className="text-[13px] text-muted-foreground">{t("check.never")}</p>;
  const packs = c.missing_packs.length;
  const models = c.missing_models.length;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3 text-[13px]">
        <span className="text-muted-foreground">
          {t("check.last", {
            time: formatDateTime(c.at),
            found: c.node_classes.found,
            total: c.node_classes.total,
          })}
        </span>
        <Button
          size="sm"
          variant="outline"
          disabled={run.isPending}
          onClick={() =>
            run.mutate(undefined, {
              onSuccess: () => toast.success(t("check.done", { name: w.name })),
              onError,
            })
          }
        >
          {t("check.run")}
        </Button>
      </div>
      {!packs && !models && !c.problems.length ? (
        <p className="text-[13px] text-tone-pass-fg">{t("check.okLine")}</p>
      ) : null}
      {packs ? (
        <div className="flex flex-col gap-1.5">
          <h4 className="text-sm font-bold">{t("check.packs")}</h4>
          <table className="w-full text-[13px]" aria-label={t("check.packs")}>
            <thead className="text-left text-xs text-muted-foreground">
              <tr>
                <th className="py-1 pr-3 font-medium">{t("check.col.name")}</th>
                <th className="py-1 pr-3 font-medium">{t("check.col.classes")}</th>
                <th className="py-1 pr-3 font-medium">{t("check.col.source")}</th>
                <th className="py-1 font-medium">{t("check.col.version")}</th>
              </tr>
            </thead>
            <tbody>
              {c.missing_packs.map((p) => (
                <tr key={p.name} className="border-t border-border/60">
                  <td className="py-1 pr-3 font-medium">{p.name}</td>
                  <td className="py-1 pr-3 font-mono text-xs">{p.classes.join(", ")}</td>
                  <td className="py-1 pr-3 text-muted-foreground">{p.source}</td>
                  <td className="py-1 font-mono text-xs">{p.version ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {models ? (
        <div className="flex flex-col gap-1.5">
          <h4 className="text-sm font-bold">{t("check.models")}</h4>
          <table className="w-full text-[13px]" aria-label={t("check.models")}>
            <thead className="text-left text-xs text-muted-foreground">
              <tr>
                <th className="py-1 pr-3 font-medium">{t("check.col.folder")}</th>
                <th className="py-1 pr-3 font-medium">{t("check.col.file")}</th>
                <th className="py-1 text-right font-medium">{t("check.col.size")}</th>
              </tr>
            </thead>
            <tbody>
              {c.missing_models.map((m) => (
                <tr key={`${m.folder}/${m.name}`} className="border-t border-border/60">
                  <td className="py-1 pr-3 text-muted-foreground">{m.folder}</td>
                  <td className="py-1 pr-3 font-mono text-xs">{m.name}</td>
                  <td className="py-1 text-right font-mono text-xs">
                    {m.size_bytes != null ? formatBytes(m.size_bytes) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {packs || models ? (
        <div className="flex flex-col gap-1.5">
          <div>
            <Button
              size="sm"
              disabled={plan.isPending || install.isPending}
              onClick={() =>
                plan.mutate(undefined, { onSuccess: (p) => setChanges(p.changes), onError })
              }
            >
              {t("check.install", { packs, models })}
            </Button>
          </div>
          <p className="text-xs leading-relaxed text-muted-foreground">{t("check.installNote")}</p>
        </div>
      ) : null}
      {changes ? (
        <ConfirmInstall
          reasons={changes}
          comfyRoot={comfy.data?.comfy?.root ?? null}
          itemName={(id) => id}
          pending={install.isPending}
          snapshotNote={t("check.snapshotNote")}
          onCancel={() => setChanges(null)}
          onConfirm={() =>
            install.mutate(undefined, {
              onSuccess: (r) => {
                setChanges(null);
                toast.success(
                  t("check.installed", { snapshot: r.snapshot, packs: r.packs, models: r.models }),
                );
              },
              onError,
            })
          }
        />
      ) : null}
    </div>
  );
}

function Trial({ w }: { w: Workflow }) {
  const { t } = useTranslation("workflows");
  const run = useTrialWorkflow(w.id);
  const setTier = useSetWorkflowTier(w.id);
  const onError = useOnError();
  const trial = w.trial;
  const pending = pendingCount(w);
  const blocked = pending
    ? t("trial.blockedPending")
    : w.check?.status !== "ok"
      ? t("trial.blockedCheck")
      : null;
  const running = trial?.status === "running";
  const draft = trial ?? { w: 768, h: 1366, seconds: 3 };
  const video = w.components.some((c) => c === "vid" || c === "up" || c === "lip");

  return (
    <div className="flex flex-col gap-3">
      <p className="text-[13px] leading-relaxed text-muted-foreground">{t("trial.lead")}</p>
      <div className="flex flex-wrap gap-5">
        <div className="flex w-[300px] flex-col gap-2">
          <h4 className="text-sm font-bold">{t("trial.inputs")}</h4>
          <div className="flex gap-2.5">
            <MediaThumb aspect="9:16" seed="trial-first-frame" label="1-04" className="w-20" />
            <div className="flex flex-col gap-1 text-[13px]">
              <span>{t("trial.prompt")}</span>
              <span className="font-mono text-xs text-muted-foreground">
                {t("trial.size", draft)}
              </span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              disabled={!!blocked || running || run.isPending}
              onClick={() =>
                run.mutate(undefined, {
                  onSuccess: () => toast.success(t("trial.started", { name: w.name })),
                  onError,
                })
              }
            >
              {trial ? t("trial.rerun") : t("trial.run")}
            </Button>
            {blocked ? <span className="text-xs text-muted-foreground">{blocked}</span> : null}
          </div>
        </div>
        <div className="flex min-w-0 flex-[1_1_300px] flex-col gap-2">
          <h4 className="text-sm font-bold">{t("trial.result")}</h4>
          {!trial ? (
            <p className="text-[13px] text-muted-foreground">{t("trial.none")}</p>
          ) : running ? (
            <p className="flex items-center gap-2 text-[13px] text-tone-info-fg">
              <Loader2 className="size-4 animate-spin" aria-hidden />
              {t("trial.running")}
            </p>
          ) : (
            <div className="flex gap-3">
              <MediaThumb
                aspect="9:16"
                seed={`trial-${w.id}`}
                label={video ? "▶" : undefined}
                caption={trial.duration_s != null ? `${trial.seconds}s` : undefined}
                className="w-24"
              />
              <div className="flex flex-col gap-2 text-[13px]">
                <StatusBadge tone={trial.status === "passed" ? "pass" : "fail"}>
                  {trial.status === "passed"
                    ? t("trial.passed", {
                        time: formatDateTime(trial.at),
                        seconds: trial.duration_s ?? "—",
                        vram: trial.vram_gb ?? "—",
                      })
                    : t("trial.failed", { time: formatDateTime(trial.at) })}
                </StatusBadge>
                {trial.status === "passed" && w.tier === "unverified" && w.source === "user" ? (
                  <div>
                    <Button
                      size="sm"
                      disabled={setTier.isPending}
                      onClick={() =>
                        setTier.mutate("mine", {
                          onSuccess: () => toast.success(t("promoted", { name: w.name })),
                          onError,
                        })
                      }
                    >
                      {t("trial.promoteNow")}
                    </Button>
                  </div>
                ) : null}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export function WorkflowDetail({ w }: { w: Workflow }) {
  const { t } = useTranslation("workflows");
  const pending = pendingCount(w);
  const missing = (w.check?.missing_packs.length ?? 0) + (w.check?.missing_models.length ?? 0);
  return (
    <div className="flex flex-col gap-3 border-t border-border/60 px-5 pt-3 pb-4">
      <Header w={w} />
      <Tabs defaultValue={pending ? "bindings" : missing ? "check" : "trial"}>
        <TabsList className="w-fit min-w-96">
          <TabsTrigger value="bindings">{t("tab.bindings")}</TabsTrigger>
          <TabsTrigger value="check">{t("tab.check")}</TabsTrigger>
          <TabsTrigger value="trial">{t("tab.trial")}</TabsTrigger>
        </TabsList>
        <TabsContent value="bindings">
          <Bindings w={w} />
        </TabsContent>
        <TabsContent value="check">
          <Check w={w} />
        </TabsContent>
        <TabsContent value="trial">
          <Trial w={w} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
