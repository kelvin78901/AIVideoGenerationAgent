/** `/` when there is no series yet: start one (the top bar's menu does the same). */
import { Clapperboard, Plus } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/EmptyState";
import { NewSeriesDialog } from "@/components/NewSeriesDialog";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";

export default function NoSeriesPage() {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  return (
    <div className="mx-auto flex w-full max-w-[880px] flex-col gap-5 px-7 py-6">
      <PageHeader title={t("noSeries.title")} lead={t("noSeries.lead")} />
      <EmptyState
        icon={Clapperboard}
        title={t("noSeries.empty")}
        description={t("noSeries.emptyLead")}
        action={
          <Button size="lg" onClick={() => setOpen(true)}>
            <Plus aria-hidden />
            {t("seriesMenu.new")}
          </Button>
        }
      />
      <NewSeriesDialog open={open} onOpenChange={setOpen} />
    </div>
  );
}
