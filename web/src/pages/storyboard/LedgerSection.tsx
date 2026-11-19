import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import type { ShotLedger } from "@/api/schemas/shots";

/** Scrolls another part of the shot settings into view (the top view, the contract). */
function jump(id: string) {
  document.getElementById(id)?.scrollIntoView?.({ block: "center", behavior: "smooth" });
}

function Tag({ children }: { children: string }) {
  return (
    <span className="rounded border border-primary/30 bg-primary/5 px-1.5 py-0.5 text-xs text-primary">
      {children}
    </span>
  );
}

function EditButton({ label, onClick }: { label: string; onClick: () => void }) {
  const { t } = useTranslation("storyboard");
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      className="text-xs text-primary hover:underline"
    >
      {t("ledger.edit")}
    </button>
  );
}

/**
 * 连续性 (M6 草图 S1): read-only, where each filmed person is when the shot starts, what they
 * hold and wear, the props' states and the time, with where each was carried from. Changing it
 * means changing what it comes from: 「去改」 goes to the top view (站位), the contract (手里,
 * 道具) or the person's asset (服装).
 */
export function LedgerSection({
  ledger,
  blockingId,
  contractId,
  assetsPath,
  labelOf,
}: {
  ledger: ShotLedger;
  /** The top view's element id. */
  blockingId: string;
  /** The contract section's element id. */
  contractId: string;
  assetsPath: string;
  /** A shot's label by its id (`*_from` are shot ids). */
  labelOf: (shotId: string) => string;
}) {
  const { t } = useTranslation("storyboard");
  const th = "py-1.5 pr-3 text-left text-xs font-medium text-muted-foreground";
  const td = "py-1.5 pr-3 align-top";
  const muted = "text-muted-foreground";
  const { time } = ledger;
  const timeOfDay = time.time_of_day
    ? t(`ledger.timeOfDay.${time.time_of_day}` as "ledger.timeOfDay.day", {
        defaultValue: time.time_of_day,
      })
    : null;

  return (
    <section aria-labelledby="ledger-title" className="flex flex-col gap-2">
      <div className="flex flex-wrap items-baseline gap-x-2">
        <h3 id="ledger-title" className="text-sm font-bold">
          {t("ledger.title")}
        </h3>
        <span className="text-xs text-muted-foreground">{t("ledger.hint")}</span>
      </div>
      {!ledger.characters.length && !ledger.props.length ? (
        <p className="text-xs text-muted-foreground">{t("ledger.empty")}</p>
      ) : null}
      {ledger.characters.length ? (
        <div className="overflow-x-auto">
          <table aria-label={t("ledger.colCharacter")} className="w-full text-sm">
            <thead>
              <tr className="border-b">
                <th className={th}>{t("ledger.colCharacter")}</th>
                <th className={th}>{t("ledger.colPosition")}</th>
                <th className={th}>{t("ledger.colFacing")}</th>
                <th className={th}>{t("ledger.colHolding")}</th>
                <th className={th}>{t("ledger.colOutfit")}</th>
              </tr>
            </thead>
            <tbody>
              {ledger.characters.map((c) => (
                <tr key={c.asset_id} className="border-b last:border-b-0">
                  <td className={td}>
                    <Tag>{c.name}</Tag>
                  </td>
                  <td className={td}>
                    <span className="flex flex-wrap items-baseline gap-x-2">
                      <span>
                        {[
                          c.position ? t(`ledger.position.${c.position}`) : null,
                          c.depth ? t(`ledger.depth.${c.depth}`) : null,
                        ]
                          .filter(Boolean)
                          .join(" · ") || "—"}
                      </span>
                      <EditButton
                        label={t("ledger.editPosition", { name: c.name })}
                        onClick={() => jump(blockingId)}
                      />
                    </span>
                  </td>
                  <td className={td}>{c.facing || "—"}</td>
                  <td className={td}>
                    <span className="flex flex-wrap items-baseline gap-x-2">
                      <span>
                        {c.holding_names.length ? c.holding_names.join("、") : "—"}
                        {c.holding_from ? (
                          <span className={muted}>
                            {t("ledger.fromShot", { id: labelOf(c.holding_from) })}
                          </span>
                        ) : null}
                      </span>
                      <EditButton
                        label={t("ledger.editHolding", { name: c.name })}
                        onClick={() => jump(contractId)}
                      />
                    </span>
                  </td>
                  <td className={td}>
                    <span className="flex flex-wrap items-baseline gap-x-2">
                      <span>
                        {c.outfit || "—"}
                        {c.outfit ? (
                          <span className={muted}>
                            {c.outfit_from
                              ? t("ledger.fromShot", { id: labelOf(c.outfit_from) })
                              : t("ledger.fromAsset")}
                          </span>
                        ) : null}
                      </span>
                      <Link
                        to={`${assetsPath}?asset=${encodeURIComponent(c.asset_id)}`}
                        aria-label={t("ledger.editOutfit", { name: c.name })}
                        className="text-xs text-primary hover:underline"
                      >
                        {t("ledger.edit")}
                      </Link>
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {ledger.props.length ? (
        <div className="overflow-x-auto">
          <table aria-label={t("ledger.colProp")} className="w-full text-sm">
            <thead>
              <tr className="border-b">
                <th className={th}>{t("ledger.colProp")}</th>
                <th className={th}>{t("ledger.colState")}</th>
                <th className={th}>{t("ledger.colFrom")}</th>
                <th className={th}>
                  <span className="sr-only">{t("ledger.edit")}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {ledger.props.map((p) => (
                <tr key={p.asset_id} className="border-b last:border-b-0">
                  <td className={td}>
                    <Tag>{p.name}</Tag>
                  </td>
                  <td className={td}>{p.state}</td>
                  <td className={`${td} ${muted}`}>
                    {p.from_shot
                      ? t("ledger.endOf", { id: labelOf(p.from_shot) })
                      : t("ledger.own")}
                  </td>
                  <td className={td}>
                    <EditButton
                      label={t("ledger.editProp", { name: p.name })}
                      onClick={() => jump(contractId)}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {timeOfDay || time.clock ? (
        <div className="flex flex-wrap items-baseline gap-x-2 text-sm">
          <span className="text-xs text-muted-foreground">{t("ledger.time")}</span>
          <span>{[timeOfDay, time.clock].filter(Boolean).join(" · ")}</span>
          {time.clock ? (
            <span className="text-xs text-muted-foreground">
              {time.clock_from
                ? t("ledger.clockFrom", { id: labelOf(time.clock_from) })
                : t("ledger.clock")}
            </span>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
