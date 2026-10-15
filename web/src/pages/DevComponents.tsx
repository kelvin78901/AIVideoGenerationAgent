/**
 * Dev-only showcase of the shared components in their states (M0.5 acceptance: every shared
 * component visible here). Registered only in dev builds.
 */
import { ArrowLeftRight, Film } from "lucide-react";
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { ApiError } from "@/api/client";
import { useLock, useProduct } from "@/api/hooks/products";
import { Chip } from "@/components/Chip";
import { CostBadge } from "@/components/CostBadge";
import { EmptyState } from "@/components/EmptyState";
import { MediaThumb } from "@/components/MediaThumb";
import { ModelSwitchMenu } from "@/components/ModelSwitchMenu";
import { PageHeader } from "@/components/PageHeader";
import { PromptEditor } from "@/components/PromptEditor";
import { QueryError, QueryState, Skeleton } from "@/components/QueryState";
import { RunBar } from "@/components/RunBar";
import { SegmentedControl } from "@/components/SegmentedControl";
import { StatusBadge, type Tone } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input, Label, Textarea } from "@/components/ui/form";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Progress } from "@/components/ui/progress";
import { RadioCard, RadioGroup } from "@/components/ui/radio-group";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { VersionHistory } from "@/components/VersionHistory";
// Dev-only page: model names come from the demo catalog until step 5's /config/components.
import { llmModels } from "@/mocks/fixtures/demo/models";
import { PRODUCT_ENRICH, PRODUCT_EXTRACT } from "@/mocks/fixtures/demo/products";

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-wrap items-start gap-3">{children}</CardContent>
    </Card>
  );
}

type Sample = (key: string, opts?: Record<string, unknown>) => string;

/** RunBar + history + prompt editor over one demo product, as the Inspector will show them. */
function ProductShowcase({
  id,
  what,
  name,
  s,
}: {
  id: string;
  what: string;
  name: string;
  s: Sample;
}) {
  const product = useProduct(id);
  const lock = useLock(id);
  const [tab, setTab] = useState<"prompt" | "history">("history");
  return (
    <QueryState query={product}>
      {(p) => (
        <div className="flex w-full flex-col gap-3">
          <RunBar
            product={p}
            what={what}
            models={llmModels}
            onEditPrompt={() => setTab("prompt")}
            onOpenHistory={() => setTab("history")}
          />
          <div className="grid gap-3 md:grid-cols-2">
            <Card>
              <CardContent className="pt-4">
                {tab === "history" ? (
                  <VersionHistory product={p} models={llmModels} componentName={name} />
                ) : (
                  <PromptEditor product={p} componentName={name} />
                )}
              </CardContent>
            </Card>
            <div className="flex flex-col items-start gap-2">
              <Button
                variant="outline"
                disabled={!p.adopted_version_id || lock.isPending}
                onClick={() => lock.mutate(p.locked_hash === null)}
              >
                {s(p.locked_hash === null ? "lock" : "unlock")}
              </Button>
            </div>
          </div>
        </div>
      )}
    </QueryState>
  );
}

export default function DevComponentsPage() {
  const { t } = useTranslation("dev");
  const { t: tNav } = useTranslation("nav");
  const [mode, setMode] = useState<"local" | "api" | "hybrid">("api");
  const [chips, setChips] = useState<Record<number, boolean>>({ 1: true });
  const [radio, setRadio] = useState("a");
  const [on, setOn] = useState(true);
  const s: Sample = (key, opts) => t(`showcase.sample.${key}` as "intro", opts);
  const tones: Tone[] = ["pass", "fail", "warn", "info", "neutral"];

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-4 p-6">
      <PageHeader title={tNav("pages.devComponents")} lead={t("showcase.intro")} />

      <Section title={t("showcase.tones")}>
        {tones.map((tone) => (
          <StatusBadge key={tone} tone={tone}>
            {s(tone)}
          </StatusBadge>
        ))}
      </Section>

      <Section title={t("showcase.cost")}>
        <CostBadge where="local" />
        <CostBadge where="local" compact />
        <CostBadge where="api" usd={0.4} />
        <CostBadge where="api" usd={0.02} estimate seconds={40} />
        <CostBadge where="api" usd={0.02} estimate compact />
        <CostBadge where="api" price={null} />
        <CostBadge where="api" price={{ unit: "mtok", in: 1.32, out: 3.96, currency: "USD" }} />
        <CostBadge where="api" price={{ unit: "mtok", in: 6, out: 30, currency: "CNY" }} />
        <CostBadge where="api" price={{ unit: "image", amount: 0.04, currency: "USD" }} />
        <CostBadge where="api" price={{ unit: "second", amount: 0.1, currency: "USD" }} />
      </Section>

      <Section title={t("showcase.products")}>
        <ProductShowcase id={PRODUCT_ENRICH} what={s("what")} name={s("enrich")} s={s} />
        <ProductShowcase id={PRODUCT_EXTRACT} what={s("whatExtract")} name={s("extract")} s={s} />
        <ModelSwitchMenu
          options={llmModels}
          currentKey="deepseek/v4-pro"
          align="start"
          onPick={(key) => toast.info(s("picked", { model: key }))}
        >
          <Button variant="outline">
            <ArrowLeftRight aria-hidden />
            {s("switchMenu")}
          </Button>
        </ModelSwitchMenu>
      </Section>

      <Section title={t("showcase.segmented")}>
        <SegmentedControl
          label={t("showcase.segmented")}
          value={mode}
          onChange={setMode}
          options={[
            { value: "local", label: s("local"), disabled: true, hint: s("noLocal") },
            { value: "api", label: s("api") },
            { value: "hybrid", label: s("hybrid") },
          ]}
        />
        <SegmentedControl
          size="sm"
          label={t("showcase.segmented")}
          value={mode}
          onChange={setMode}
          options={[
            { value: "local", label: s("local") },
            { value: "api", label: s("api") },
            { value: "hybrid", label: s("hybrid") },
          ]}
        />
      </Section>

      <Section title={t("showcase.chips")}>
        {[1, 2, 3].map((n) => (
          <Chip
            key={n}
            check
            selected={!!chips[n]}
            onClick={() => setChips((c) => ({ ...c, [n]: !c[n] }))}
          >
            {s("option", { n })}
          </Chip>
        ))}
        <div role="radiogroup" aria-label={t("showcase.chips")} className="flex gap-1.5">
          {[1, 2].map((n) => (
            <Chip key={n} role="radio" selected={n === 1}>
              {s("option", { n })}
            </Chip>
          ))}
        </div>
      </Section>

      <Section title={t("showcase.media")}>
        <div className="w-32">
          <MediaThumb aspect="9:16" seed="1-01" label="1-01" caption={s("shot", { id: "1-01" })} />
        </div>
        <div className="w-32">
          <MediaThumb aspect="9:16" seed="1-08" label="1-08" dashed />
        </div>
        <div className="w-56">
          <MediaThumb aspect="16:9" seed="1-04" label="1-04" caption={s("shot", { id: "1-04" })} />
        </div>
      </Section>

      <Section title={t("showcase.empty")}>
        <EmptyState
          className="w-full"
          icon={Film}
          title={s("emptyTitle")}
          description={s("emptyText")}
        />
      </Section>

      <Section title={t("showcase.loading")}>
        <Skeleton className="h-10 w-64" />
        <div className="w-full">
          <QueryError
            error={new ApiError(404, { code: "series_not_found", params: { id: "x" } })}
            onRetry={() => {}}
          />
        </div>
      </Section>

      <Section title={t("showcase.primitives")}>
        <div className="grid w-72 gap-2">
          <Label htmlFor="sc-input">{s("input")}</Label>
          <Input id="sc-input" defaultValue="0.5" />
          <Textarea defaultValue={s("emptyText")} />
        </div>
        <div className="grid w-64 gap-3">
          <Label>
            <Switch checked={on} onCheckedChange={setOn} />
            {s("switch")}
          </Label>
          <Label>
            <Checkbox defaultChecked />
            {s("checkbox")}
          </Label>
          <Slider defaultValue={[80]} max={100} aria-label={s("input")} />
          <Progress value={47} aria-label={s("input")} />
        </div>
        <RadioGroup value={radio} onValueChange={setRadio} className="w-64">
          {["a", "b"].map((v, i) => (
            <RadioCard key={v} value={v}>
              <div className="font-medium">{s("option", { n: i + 1 })}</div>
              <div className="text-xs text-muted-foreground">{s("emptyText")}</div>
            </RadioCard>
          ))}
        </RadioGroup>
        <div className="flex gap-2">
          <Dialog>
            <DialogTrigger asChild>
              <Button variant="outline">{s("dialog")}</Button>
            </DialogTrigger>
            <DialogContent closeLabel={s("close")}>
              <DialogHeader>
                <DialogTitle>{s("dialogTitle")}</DialogTitle>
                <DialogDescription>{s("dialogText")}</DialogDescription>
              </DialogHeader>
            </DialogContent>
          </Dialog>
          <Popover>
            <PopoverTrigger asChild>
              <Button variant="outline">{s("popover")}</Button>
            </PopoverTrigger>
            <PopoverContent>{s("popoverText")}</PopoverContent>
          </Popover>
        </div>
      </Section>
    </div>
  );
}
