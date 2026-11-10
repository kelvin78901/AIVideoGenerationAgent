/**
 * The key dialog's lower half (M5 step 7a, not in the prototype): the models the provider's own
 * list returned — pick which ones the studio can use, see each one's price, fill in a price for
 * the ones nobody priced — and the media models on this key, whose model id can be changed.
 */
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { errorMessage } from "@/api/client";
import { usePickProviderModels, useSetModelSetting } from "@/api/hooks/config";
import type { ListedModel, Provider, TokenPrice } from "@/api/schemas/providers";
import { SegmentedControl } from "@/components/SegmentedControl";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input, Label } from "@/components/ui/form";
import { formatPrice } from "@/lib/cost";
import { formatDateTime } from "@/lib/format";

/** Past this many models (OpenRouter lists hundreds) a filter box appears. */
const FILTER_FROM = 12;

export function ProviderModels({ provider: p }: { provider: Provider }) {
  const { t } = useTranslation("models");
  const { t: tc } = useTranslation();
  const pick = usePickProviderModels(p.id);
  const [filter, setFilter] = useState("");
  const listed = p.listed;
  if (p.where !== "api") return null;
  if (!listed) {
    return <p className="text-xs leading-relaxed text-muted-foreground">{t("list.none")}</p>;
  }
  const picked = listed.models.filter((m) => m.enabled).map((m) => m.model_id);
  const toggle = (id: string, on: boolean) =>
    pick.mutate(on ? [...picked, id] : picked.filter((x) => x !== id), {
      onError: (err) => toast.error(errorMessage(tc, err)),
    });
  const needle = filter.trim().toLowerCase();
  const shown = needle
    ? listed.models.filter((m) => `${m.model_id} ${m.display}`.toLowerCase().includes(needle))
    : listed.models;

  return (
    <section aria-labelledby={`models-${p.id}`} className="flex flex-col gap-2">
      <div className="flex flex-wrap items-baseline gap-x-2">
        <h3 id={`models-${p.id}`} className="text-sm font-medium">
          {t("list.title")}
        </h3>
        <span className="text-xs text-muted-foreground">
          {t("list.count", { count: listed.models.length, picked: picked.length })}
          {listed.fetched_at
            ? ` · ${t("list.fetched", { time: formatDateTime(listed.fetched_at) })}`
            : null}
        </span>
      </div>
      <p className="text-xs leading-relaxed text-muted-foreground">{t("list.lead")}</p>
      {listed.models.length > FILTER_FROM ? (
        <Input
          aria-label={t("list.filter")}
          placeholder={t("list.filter")}
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="h-8"
        />
      ) : null}
      <ul
        aria-label={t("list.title")}
        aria-busy={pick.isPending || undefined}
        className="flex max-h-72 flex-col divide-y overflow-y-auto rounded-md border"
      >
        {shown.map((m) => (
          <ListedRow
            key={m.model_id}
            model={m}
            busy={pick.isPending}
            onToggle={(on) => toggle(m.model_id, on)}
          />
        ))}
        {shown.length === 0 ? (
          <li className="px-3 py-2 text-xs text-muted-foreground">{t("list.empty")}</li>
        ) : null}
      </ul>
    </section>
  );
}

function ListedRow({
  model: m,
  busy,
  onToggle,
}: {
  model: ListedModel;
  busy: boolean;
  onToggle: (on: boolean) => void;
}) {
  const { t } = useTranslation("models");
  const { t: tp } = useTranslation("components");
  const { t: tc } = useTranslation();
  const setting = useSetModelSetting();
  const [editing, setEditing] = useState(false);
  const id = `pick-${m.key}`;
  const priceText = m.price
    ? formatPrice(tp, {
        unit: "mtok",
        in: m.price.in,
        out: m.price.out,
        currency: m.price.currency === "CNY" ? "CNY" : "USD",
      })
    : null;
  const clear = () =>
    setting.mutate(
      { key: m.key, price: null },
      {
        onSuccess: () => toast.success(t("price.cleared", { model: m.display })),
        onError: (err) => toast.error(errorMessage(tc, err)),
      },
    );

  return (
    <li className="flex flex-col gap-2 px-3 py-2">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <Checkbox
          id={id}
          checked={m.enabled}
          disabled={busy}
          onCheckedChange={(on) => onToggle(on === true)}
        />
        <Label htmlFor={id} className="min-w-0 flex-1 font-normal">
          <span className="text-sm">{m.display}</span>
          {m.display !== m.model_id ? (
            <span className="ml-1.5 font-mono text-xs text-muted-foreground">{m.model_id}</span>
          ) : null}
        </Label>
        <span className="flex items-center gap-1.5 text-xs">
          {m.price_source === null ? (
            <StatusBadge tone="warn" icon={null}>
              {t("price.unknown")}
            </StatusBadge>
          ) : (
            <span className="text-muted-foreground tabular-nums">
              {t(m.price_source === "user" ? "price.user" : "price.table", { price: priceText })}
            </span>
          )}
          {!editing ? (
            <Button
              variant="link"
              size="sm"
              className="h-auto p-0 text-xs"
              aria-label={t(m.price_source === null ? "price.fillFor" : "price.editFor", {
                model: m.display,
              })}
              onClick={() => setEditing(true)}
            >
              {t(m.price_source === null ? "price.fill" : "price.edit")}
            </Button>
          ) : null}
          {m.price_source === "user" && !editing ? (
            <Button
              variant="link"
              size="sm"
              className="h-auto p-0 text-xs text-muted-foreground"
              disabled={setting.isPending}
              onClick={clear}
            >
              {t("price.clear")}
            </Button>
          ) : null}
        </span>
      </div>
      {editing ? (
        <PriceForm
          model={m}
          onDone={() => setEditing(false)}
          save={(price) =>
            setting.mutate(
              { key: m.key, price },
              {
                onSuccess: () => {
                  setEditing(false);
                  toast.success(t("price.saved", { model: m.display }));
                },
                onError: (err) => toast.error(errorMessage(tc, err)),
              },
            )
          }
          busy={setting.isPending}
        />
      ) : null}
    </li>
  );
}

function PriceForm({
  model: m,
  save,
  onDone,
  busy,
}: {
  model: ListedModel;
  save: (price: TokenPrice) => void;
  onDone: () => void;
  busy: boolean;
}) {
  const { t } = useTranslation("models");
  const [input, setInput] = useState(m.price?.in.toString() ?? "");
  const [output, setOutput] = useState(m.price?.out.toString() ?? "");
  const [currency, setCurrency] = useState<"CNY" | "USD">(
    m.price?.currency === "USD" ? "USD" : "CNY",
  );
  const n = (s: string) => (s.trim() === "" ? NaN : Number(s));
  const ok = [n(input), n(output)].every((v) => Number.isFinite(v) && v >= 0);

  return (
    <form
      aria-label={t("price.formFor", { model: m.display })}
      className="flex flex-wrap items-end gap-2 pl-7"
      onSubmit={(e) => {
        e.preventDefault();
        if (ok) save({ in: n(input), out: n(output), currency });
      }}
    >
      <label className="flex flex-col gap-1 text-xs">
        {t("price.in")}
        <Input
          type="number"
          min={0}
          step="any"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          className="h-8 w-24"
        />
      </label>
      <label className="flex flex-col gap-1 text-xs">
        {t("price.out")}
        <Input
          type="number"
          min={0}
          step="any"
          value={output}
          onChange={(e) => setOutput(e.target.value)}
          className="h-8 w-24"
        />
      </label>
      <SegmentedControl
        size="sm"
        label={t("price.currency")}
        value={currency}
        onChange={setCurrency}
        options={[
          { value: "CNY", label: "¥" },
          { value: "USD", label: "$" },
        ]}
      />
      <span className="pb-2 text-xs text-muted-foreground">{t("price.unit")}</span>
      <div className="flex gap-1.5">
        <Button type="submit" size="sm" disabled={!ok || busy}>
          {t("price.save")}
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={onDone}>
          {t("price.cancel")}
        </Button>
      </div>
    </form>
  );
}

/** Media models on this key: the model id each one calls, which can be changed (a newer
 * version); providers with a list offer its ids as suggestions. */
export function MediaModelIds({ provider: p }: { provider: Provider }) {
  const { t } = useTranslation("models");
  if (!p.media.length) return null;
  const suggestions = p.listed?.models.map((m) => m.model_id) ?? [];
  const listId = `media-ids-${p.id}`;
  return (
    <section aria-labelledby={`media-${p.id}`} className="flex flex-col gap-2">
      <h3 id={`media-${p.id}`} className="text-sm font-medium">
        {t("media.title")}
      </h3>
      <p className="text-xs leading-relaxed text-muted-foreground">
        {t(suggestions.length ? "media.leadListed" : "media.lead")}
      </p>
      {suggestions.length ? (
        <datalist id={listId}>
          {suggestions.map((id) => (
            <option key={id} value={id} />
          ))}
        </datalist>
      ) : null}
      <ul className="flex flex-col gap-1.5">
        {p.media.map((m) => (
          <MediaRow key={`${m.key}:${m.model_id ?? ""}`} media={m} listId={listId} />
        ))}
      </ul>
    </section>
  );
}

function MediaRow({ media: m, listId }: { media: Provider["media"][number]; listId: string }) {
  const { t } = useTranslation("models");
  const { t: tc } = useTranslation();
  const setting = useSetModelSetting();
  const [value, setValue] = useState(m.model_id ?? "");
  const changed = value.trim() !== "" && value.trim() !== (m.model_id ?? "");
  const onError = (err: unknown) => toast.error(errorMessage(tc, err));
  const id = `media-id-${m.key}`;
  return (
    <li className="flex flex-wrap items-center gap-2">
      <Label htmlFor={id} className="w-40 shrink-0 text-sm font-normal">
        {m.display}
      </Label>
      <Input
        id={id}
        list={listId}
        spellCheck={false}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        className="h-8 min-w-0 flex-1 font-mono text-xs"
      />
      {m.custom_model_id ? (
        <StatusBadge tone="info" icon={null}>
          {t("media.custom")}
        </StatusBadge>
      ) : null}
      <Button
        size="sm"
        variant="outline"
        disabled={!changed || setting.isPending}
        onClick={() =>
          setting.mutate(
            { key: m.key, model_id: value.trim() },
            {
              onSuccess: () => toast.success(t("media.saved", { name: m.display, id: value })),
              onError,
            },
          )
        }
      >
        {t("media.save")}
      </Button>
      {m.custom_model_id ? (
        <Button
          size="sm"
          variant="ghost"
          disabled={setting.isPending}
          onClick={() =>
            setting.mutate(
              { key: m.key, model_id: null },
              { onSuccess: () => toast.success(t("media.reset", { name: m.display })), onError },
            )
          }
        >
          {t("media.resetButton")}
        </Button>
      ) : null}
    </li>
  );
}
