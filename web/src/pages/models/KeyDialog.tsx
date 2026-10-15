/**
 * API key for one writing-model provider (not in the prototype): save, delete, test the
 * connection. Talks to the real backend (M0); the key is write-only and never shown again.
 */
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { errorMessage } from "@/api/client";
import { useDeleteProviderKey, useSaveProviderKey, useTestProvider } from "@/api/hooks/config";
import type { Provider } from "@/api/schemas/providers";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input, Label } from "@/components/ui/form";

export function KeyDialog({
  provider,
  onOpenChange,
}: {
  provider: Provider | null;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog open={!!provider} onOpenChange={onOpenChange}>
      {provider ? <KeyForm key={provider.id} provider={provider} /> : null}
    </Dialog>
  );
}

function KeyForm({ provider: p }: { provider: Provider }) {
  const { t } = useTranslation("models");
  const { t: tc } = useTranslation();
  const [key, setKey] = useState("");
  const save = useSaveProviderKey(p.id);
  const remove = useDeleteProviderKey(p.id);
  const test = useTestProvider(p.id);
  const onError = (err: unknown) => toast.error(errorMessage(tc, err));
  const busy = save.isPending || remove.isPending;

  const onSave = (e: React.FormEvent) => {
    e.preventDefault();
    if (!key.trim()) return;
    save.mutate(key.trim(), {
      onSuccess: () => {
        setKey("");
        test.reset();
        toast.success(t("key.saved", { name: p.name }));
      },
      onError,
    });
  };

  const result = test.data;
  return (
    <DialogContent>
      <DialogHeader>
        <DialogTitle>{t("key.title", { name: p.name })}</DialogTitle>
        <DialogDescription>{t("key.lead")}</DialogDescription>
      </DialogHeader>
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <StatusBadge tone={p.has_key ? "info" : "warn"} icon={null}>
            {t(`key.status.${p.key_source}`)}
          </StatusBadge>
          {p.docs ? (
            <a
              href={p.docs}
              target="_blank"
              rel="noreferrer"
              className="text-primary underline-offset-4 hover:underline"
            >
              {t("key.docs")}
            </a>
          ) : null}
        </div>
        {p.base_url ? (
          <p className="font-mono text-xs break-all text-muted-foreground">
            {t("key.baseUrl", { url: p.base_url })}
          </p>
        ) : null}
        <form onSubmit={onSave} className="flex flex-col gap-1.5">
          <Label htmlFor="provider-key">{t("key.input")}</Label>
          <div className="flex gap-2">
            <Input
              id="provider-key"
              type="password"
              autoComplete="off"
              spellCheck={false}
              placeholder={t("key.placeholder")}
              value={key}
              onChange={(e) => setKey(e.target.value)}
              className="font-mono"
            />
            <Button type="submit" disabled={!key.trim() || busy}>
              {t(p.has_key ? "key.replace" : "key.save")}
            </Button>
          </div>
        </form>
        {p.key_source === "env" ? (
          <p className="text-xs text-muted-foreground">{t("key.envNote")}</p>
        ) : null}
        {result ? (
          <p
            role="status"
            className={result.ok ? "text-sm text-tone-info-fg" : "text-sm text-tone-warn-fg"}
          >
            {result.ok
              ? result.models.length
                ? t("key.testOk", { count: result.models.length })
                : t("key.testOkNoList")
              : t("key.testFail", { detail: result.detail ?? "" })}
          </p>
        ) : null}
      </div>
      <DialogFooter className="gap-2 sm:justify-between">
        <Button
          variant="outline"
          disabled={!p.has_key || test.isPending}
          onClick={() => test.mutate(undefined, { onError })}
        >
          {test.isPending ? t("key.testing") : t("key.test")}
        </Button>
        {p.key_source === "keyring" ? (
          <Button
            variant="ghost"
            disabled={busy}
            onClick={() =>
              remove.mutate(undefined, {
                onSuccess: () => {
                  test.reset();
                  toast.success(t("key.deleted", { name: p.name }));
                },
                onError,
              })
            }
          >
            {t("key.delete")}
          </Button>
        ) : null}
      </DialogFooter>
    </DialogContent>
  );
}
