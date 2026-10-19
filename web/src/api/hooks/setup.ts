/** First run (SPEC 12): machine profile, scan, install (with approval), retry / skip. */
import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";

import { api, post } from "@/api/client";
import { comfyKeys } from "@/api/hooks/comfy";
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

/**
 * Applies a `setup.progress` event to the cached profile. A finished phase refetches it, and the
 * ComfyUI view: a scan identifies it again, an install may have taken a snapshot.
 */
export function applySetupProgress(client: QueryClient, ev: SetupProgress): void {
  client.setQueryData<MachineProfile>(setupKeys.profile, (p) => {
    if (!p) return p;
    const items = ev.item ? p.items.map((x) => (x.id === ev.item?.id ? ev.item : x)) : p.items;
    return { ...p, phase: ev.phase, items };
  });
  if (ev.phase === "scanned" || ev.phase === "done") {
    void client.invalidateQueries({ queryKey: setupKeys.profile });
    void client.invalidateQueries({ queryKey: comfyKeys.all });
  }
}

/** `resetsComfy`: the ComfyUI view belongs to the old machine (the sample machine switch). */
function useProfileMutation<V>(
  fn: (vars: V) => Promise<MachineProfile>,
  { resetsComfy = false }: { resetsComfy?: boolean } = {},
) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: (p) => {
      client.setQueryData(setupKeys.profile, p);
      if (resetsComfy) void client.invalidateQueries({ queryKey: comfyKeys.all });
    },
  });
}

/** `POST /setup/scan`: read-only; items arrive one by one as `setup.progress`. */
export const useScan = () => useProfileMutation(() => post("/setup/scan", MachineProfileSchema));

/** Starts at once, or waits in `install.confirm` for `useConfirmInstall` / `useCancelInstall`. */
export const useInstall = () =>
  useProfileMutation((body: InstallRequest) => post("/setup/install", MachineProfileSchema, body));

export const useConfirmInstall = () =>
  useProfileMutation(() => post("/setup/install/confirm", MachineProfileSchema));

/** Declined: nothing is installed, the page is back at the scan result. */
export const useCancelInstall = () =>
  useProfileMutation(() => post("/setup/install/cancel", MachineProfileSchema));

export const useRetrySetupItem = () =>
  useProfileMutation((id: string) => post(`/setup/items/${enc(id)}/retry`, MachineProfileSchema));

export const useSkipSetupItem = () =>
  useProfileMutation((id: string) => post(`/setup/items/${enc(id)}/skip`, MachineProfileSchema));

/** Mock only (`profile.simulated`): the prototype's sample machine switch; starts over. */
export const useSampleMachine = () =>
  useProfileMutation(
    (machine: "pc" | "mac") => post("/dev/setup/machine", MachineProfileSchema, { machine }),
    { resetsComfy: true },
  );
