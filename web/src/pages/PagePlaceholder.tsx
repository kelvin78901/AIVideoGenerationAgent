import { useTranslation } from "react-i18next";

import type { resources } from "@/i18n";

export type PageKey = keyof (typeof resources)["zh-CN"]["nav"]["pages"];

interface Props {
  page: PageKey;
  milestone: string;
  prototype?: string;
}

/** Empty page shell used until the page's milestone is built. */
export function PagePlaceholder({ page, milestone, prototype }: Props) {
  const { t } = useTranslation();
  const { t: tNav } = useTranslation("nav");
  return (
    <section className="mx-auto flex max-w-3xl flex-col gap-2 p-8">
      <h1 className="text-xl font-semibold">{tNav(`pages.${page}`)}</h1>
      <p className="text-muted-foreground">{t("placeholder.comingSoon", { milestone })}</p>
      {prototype ? (
        <p className="text-muted-foreground">
          {t("placeholder.prototype", { file: `prototype/${prototype}` })}
        </p>
      ) : null}
    </section>
  );
}
