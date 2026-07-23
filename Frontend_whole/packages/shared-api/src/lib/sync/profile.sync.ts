/**
 * Profile Sync Module
 *
 * Owns: profile, addresses query keys.
 * Subscribes to: PROFILE_UPDATED, ADDRESS_CHANGED.
 */
import { queryKeys } from "../api/queryKeys";
import { SyncEventType } from "./events";
import type { SyncBus } from "./SyncBus";

export function registerProfileSync(bus: SyncBus): void {
  const qc = bus.queryClient;

  bus.subscribe(SyncEventType.PROFILE_UPDATED, () => {
    qc.invalidateQueries({ queryKey: queryKeys.profile.me });
  });

  bus.subscribe(SyncEventType.ADDRESS_CHANGED, () => {
    qc.invalidateQueries({ queryKey: queryKeys.addresses.all });
  });
}
