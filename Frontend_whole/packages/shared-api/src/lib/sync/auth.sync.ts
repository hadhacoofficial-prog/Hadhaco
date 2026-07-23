/**
 * Auth Sync Module
 *
 * Owns: profile, addresses, orders on login/logout.
 * Subscribes to: LOGIN, LOGOUT.
 *
 * On logout, clears the entire query cache to prevent stale
 * auth-gated data leaking between accounts.
 */
import { queryKeys } from "../api/queryKeys";
import { SyncEventType } from "./events";
import type { SyncBus } from "./SyncBus";

export function registerAuthSync(bus: SyncBus): void {
  const qc = bus.queryClient;

  bus.subscribe(SyncEventType.LOGIN, () => {
    qc.invalidateQueries({ queryKey: queryKeys.profile.me });
    qc.invalidateQueries({ queryKey: queryKeys.addresses.all });
    qc.invalidateQueries({ queryKey: queryKeys.orders.all });
    qc.invalidateQueries({ queryKey: queryKeys.cart.all });
    qc.invalidateQueries({ queryKey: queryKeys.wishlist.all });
  });

  bus.subscribe(SyncEventType.LOGOUT, () => {
    // Nuclear option — clear everything so no stale auth-gated data leaks
    qc.clear();
  });
}
