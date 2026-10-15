/** 同步到哪里: one card per target with its switch, what detection found, and what it gets. */
import { AlertTriangle, Check, Minus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { errorMessage } from "@/api/client";
import { useDetectTarget, useSaveSyncSettings } from "@/api/hooks/sync";
import type { Message } from "@/api/schemas/common";
import type { SyncTarget } from "@/api/schemas/sync";
import { Chip } from "@/components/Chip";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";

const MODES = ["fcpxml", "api"] as const;
const stateIcon = { ok: Check, warn: AlertTriangle, missing: Minus };
const stateClass = {
  ok: "text-tone-pass-fg",
  warn: "text-tone-warn-fg",
  missing: "text-muted-foreground",
};

export function Targets({ targets, series }: { targets: SyncTarget[]; series: string }) {
  const { t } = useTranslation("sync");
  const { t: tc } = useTranslation();
  const save = useSaveSyncSettings();
  const detect = useDetectTarget();
  const status = (m: Message) =>
    t(`status.${m.code}` as "status.eagle_missing", { ...m.params, defaultValue: m.code });
  const onError = (err: unknown) => toast.error(errorMessage(tc, err));

  return (
    <section aria-labelledby="targets-title" className="flex flex-col gap-2.5">
      <h2 id="targets-title" className="text-base font-bold">
        {t("targets.title")}
      </h2>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(260px,1fr))] gap-3">
        {targets.map((x) => {
          const name = t(`targets.name.${x.id}`);
          const Icon = stateIcon[x.state];
          return (
            <section
              key={x.id}
              aria-label={name}
              className={cn(
                "flex flex-col gap-2.5 rounded-xl border bg-card p-4",
                x.enabled && "border-tone-info-border",
              )}
            >
              <div className="flex items-center gap-2.5">
                <span className="mr-auto text-[15px] font-bold">{name}</span>
                <span className="rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground">
                  {t(`targets.direction.${x.direction}`)}
                </span>
                <Switch
                  checked={x.enabled}
                  aria-label={t(x.enabled ? "targets.switchOn" : "targets.switchOff", { name })}
                  onCheckedChange={(on) => {
                    if (on && x.state === "missing") {
                      toast.warning(t("targets.missing", { name }));
                      return;
                    }
                    save.mutate({ targets: [{ id: x.id, enabled: on }] }, { onError });
                  }}
                />
              </div>
              <div
                className={cn(
                  "flex items-start gap-1.5 text-[13px] leading-relaxed",
                  stateClass[x.state],
                )}
              >
                <Icon className="mt-1 size-3.5 shrink-0" aria-hidden />
                <span>{status(x.status)}</span>
              </div>
              <p className="text-[13px] leading-relaxed text-muted-foreground">
                {t(`targets.what.${x.id}`, { series })}
              </p>
              {x.mode ? (
                <div
                  role="radiogroup"
                  aria-label={t("targets.mode.label")}
                  className="flex flex-wrap gap-1.5"
                >
                  {MODES.map((m) => {
                    const blocked = x.unavailable_modes[m];
                    return (
                      <Chip
                        key={m}
                        role="radio"
                        selected={x.mode === m}
                        className="min-h-9 text-[13px]"
                        onClick={() => {
                          if (blocked) toast.info(status(blocked));
                          else if (x.mode !== m)
                            save.mutate({ targets: [{ id: x.id, mode: m }] }, { onError });
                        }}
                      >
                        {t(`targets.mode.${m}`)}
                      </Chip>
                    );
                  })}
                </div>
              ) : null}
              {x.state === "missing" ? (
                <Button
                  variant="outline"
                  size="sm"
                  className="self-start"
                  disabled={detect.isPending}
                  onClick={() =>
                    detect.mutate(x.id, {
                      onSuccess: (r) => {
                        if (r.state === "missing") toast.info(status(r.status));
                      },
                      onError,
                    })
                  }
                >
                  {t("targets.redetect")}
                </Button>
              ) : null}
            </section>
          );
        })}
      </div>
    </section>
  );
}
