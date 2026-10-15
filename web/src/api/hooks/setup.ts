/** First run (SPEC 12): machine profile, scan, install, retry / skip. */
import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";

import { api, post } from "@/api/client";
import {
  MachineProfileSchema,
  type InstallRequest,
  type MachineProfile,
  type SetupProgress,
} from "@/api/schemas/setup";

const enc = encodeURIComponent;

export const setupKeys = {
  profile: ["setup", "profile"] as const,
};

export function useMachineProfile() {
  return useQuery({
    queryKey: setupKeys.profile,
    queryFn: () => api("/setup/profile", MachineProfileSchema),
  });
}

/** Applies a `setup.progress` event to the cached profile; a finished phase refetches it. */
export function applySetupProgress(client: QueryClient, ev: SetupProgress): void {
  client.setQueryData<MachineProfile>(setupKeys.profile, (p) => {
    if (!p) return p;
    const items = ev.item ? p.items.map((x) => (x.id === ev.item?.id ? ev.item : x)) : p.items;
    return { ...p, phase: ev.phase, items };
  });
  if (ev.phase === "scanned" || ev.phase === "done")
    void client.invalidateQueries({ queryKey: setupKeys.profile });
}

function useProfileMutation<V>(fn: (vars: V) => Promise<MachineProfile>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: (p) => client.setQueryData(setupKeys.profile, p),
  });
}

/** `POST /setup/scan`: read-only; items arrive one by one as `setup.progress`. */
export const useScan = () => useProfileMutation(() => post("/setup/scan", MachineProfileSchema));

export const useInstall = () =>
  useProfileMutation((body: InstallRequest) => post("/setup/install", MachineProfileSchema, body));

export const useRetrySetupItem = () =>
  useProfileMutation((id: string) => post(`/setup/items/${enc(id)}/retry`, MachineProfileSchema));

export const useSkipSetupItem = () =>
  useProfileMutation((id: string) => post(`/setup/items/${enc(id)}/skip`, MachineProfileSchema));

/** Demo only (MSW): the prototype's sample machine switch. */
export const useDemoMachine = () =>
  useProfileMutation((machine: "pc" | "mac") =>
    post("/demo/setup/machine", MachineProfileSchema, { machine }),
  );
