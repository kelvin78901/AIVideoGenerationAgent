import { useEffect, useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { errorMessage } from "@/api/client";
import { useCompilePreview, useSavePrompt } from "@/api/hooks/products";
import type { Product } from "@/api/schemas/products";
import { useRunAction } from "@/components/useRunAction";
import { Button } from "@/components/ui/button";
import { Label, Textarea } from "@/components/ui/form";
import { cn } from "@/lib/utils";

function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return debounced;
}

/**
 * 「改提示词」 (SPEC 8): the intent layer in the user's words, and the compiled layer the model
 * receives. Editing the compiled layer marks it hand-edited until 「恢复自动编译」.
 * Remounts per product, so drafts never leak between products.
 */
export function PromptEditor(props: {
  product: Product;
  /** 「小说补全」 */
  componentName: string;
  className?: string;
}) {
  return <PromptEditorForm key={props.product.id} {...props} />;
}

function PromptEditorForm({
  product,
  componentName,
  className,
}: {
  product: Product;
  componentName: string;
  className?: string;
}) {
  const { t } = useTranslation("components");
  const { t: tc } = useTranslation();
  const ids = useId();
  const saved = product.prompt;
  const [intent, setIntent] = useState(saved?.intent ?? "");
  const [manual, setManual] = useState<string | null>(
    saved?.compiled_overridden ? saved.compiled : null,
  );
  const [advanced, setAdvanced] = useState(manual !== null);
  const preview = useCompilePreview(product.id, useDebounced(intent, 300), saved?.model_key);
  const save = useSavePrompt(product.id);
  const action = useRunAction(product.id);
  const busy = action.pending || product.running !== null;

  const auto =
    preview.data?.compiled ??
    (saved && !saved.compiled_overridden && saved.intent === intent ? saved.compiled : "");
  const compiled = manual ?? auto;

  return (
    <div className={cn("flex flex-col gap-3.5", className)}>
      <div className="flex flex-col gap-1">
        <h2 className="text-base font-bold">{t("prompt.title", { name: componentName })}</h2>
        <p className="text-sm leading-relaxed text-muted-foreground">{t("prompt.lead")}</p>
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={`${ids}-intent`}>{t("prompt.intent")}</Label>
        <Textarea
          id={`${ids}-intent`}
          rows={7}
          value={intent}
          onChange={(e) => setIntent(e.target.value)}
        />
      </div>
      <Button
        variant="link"
        className="h-auto self-start p-0 text-xs"
        aria-expanded={advanced}
        onClick={() => setAdvanced(!advanced)}
      >
        {t(advanced ? "prompt.hideCompiled" : "prompt.showCompiled")}
      </Button>
      {advanced ? (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={`${ids}-compiled`} className="text-xs font-normal text-muted-foreground">
            {t("prompt.compiled")}
          </Label>
          <Textarea
            id={`${ids}-compiled`}
            rows={12}
            className="font-mono text-xs"
            value={compiled}
            onChange={(e) => setManual(e.target.value)}
          />
          {manual !== null ? (
            <div className="flex flex-wrap items-center gap-2 text-xs text-tone-warn-fg">
              {t("prompt.overridden")}
              <Button size="sm" variant="outline" onClick={() => setManual(null)}>
                {t("prompt.restore")}
              </Button>
            </div>
          ) : null}
        </div>
      ) : (
        <div className="flex flex-col gap-1.5">
          <div className="text-xs text-muted-foreground">{t("prompt.preview")}</div>
          <pre
            data-testid="compiled-preview"
            className="max-h-64 overflow-auto rounded-md bg-muted p-2.5 font-mono text-xs leading-relaxed whitespace-pre-wrap"
          >
            {compiled}
          </pre>
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        <Button
          disabled={busy}
          onClick={() => action.run({ mode: "rerun", intent, compiled: manual ?? undefined })}
        >
          {t("prompt.saveRun")}
        </Button>
        <Button
          variant="outline"
          disabled={save.isPending}
          onClick={() =>
            save.mutate(
              { intent, compiled: manual },
              {
                onSuccess: () => toast.success(t("prompt.saved")),
                onError: (err) => toast.error(errorMessage(tc, err)),
              },
            )
          }
        >
          {t("prompt.saveOnly")}
        </Button>
      </div>
    </div>
  );
}
