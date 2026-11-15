// API client
export { api } from "./lib/api/client";
export type { RequestOptions, ApiClient } from "./lib/api/client";
export { ApiError, isApiError, toUserMessage } from "./lib/api/errors";
export type { ApiErrorKind } from "./lib/api/errors";
export { queryKeys } from "./lib/api/queryKeys";
export { ENV, hasApi } from "./config/env";

// Centralized synchronization engine
export {
  initSync,
  onSyncEvent,
  afterCartChange,
  afterInventoryChange,
  afterOrderCreated,
  afterOrderCancelled,
  afterOrderStatusChanged,
  afterReservationCreated,
  afterReservationExpired,
  afterWishlistChange,
  afterProfileUpdate,
  afterAddressChange,
  afterProductUpdate,
  afterPriceChanged,
  afterCollectionUpdate,
  afterCmsPublish,
  afterReviewSubmit,
  afterLogin,
  afterLogout,
  invalidateAll,
  getBus,
} from "./lib/sync";
export { SyncEventType } from "./lib/sync";
export type { SyncEvent, SyncEventPayloads } from "./lib/sync";
export type { SyncBus } from "./lib/sync";

// Auth actions (first-party, HttpOnly-cookie sessions)
export {
  signInWithPassword,
  signUpWithPassword,
  signInWithGoogle,
  signOut,
  requestPasswordReset,
  resetPassword,
  changePassword,
  verifyEmail,
  resendVerification,
} from "./lib/auth/actions";
export { subscribeSession as onAuthStateChange } from "./lib/auth/store";
export type { AuthSession, AuthUser, AuthSurface, RegisterResult } from "./lib/auth/types";

// Session helpers
export { getSession, getUserId } from "./lib/auth/session";

// Auth providers
export { AuthProvider } from "./providers/AuthProvider";
export { AuthContext, useAuthContext } from "./providers/auth-context";
export type { AuthContextValue } from "./providers/auth-context";

// Hooks
export { useProfile } from "./hooks/auth/useProfile";
export { useNavbarCategories } from "./hooks/categories/useNavbarCategories";
export { useNavigationCategories } from "./hooks/categories/useNavigationCategories";
export * from "./hooks/cms/useCmsSection";
export * from "./hooks/cms/useCmsSections";
export * from "./hooks/cms/useHomepage";
export * from "./hooks/cms/useMedia";
// Admin hooks
export {
  useConfirmPayment,
  useMarkPacking,
  useGenerateShippingLabel,
  useGeneratePackingSlip,
  useDispatchOrder,
  useMarkInTransit,
  useMarkDelivered,
  useFulfillmentTimeline,
} from "./hooks/admin/useFulfillment";
export { useCompanyConfig, useUpdateCompanyConfig } from "./hooks/admin/useCompanyConfig";
export { usePublicCompanyConfig } from "./hooks/company/usePublicCompanyConfig";
export * from "./hooks/admin/useNotificationAdmin";
export {
  useTwoFactorStatus,
  useTwoFactorSetup,
  useTwoFactorVerify,
  useTwoFactorValidate,
  useTwoFactorDisable,
  useTwoFactorRegenerateCodes,
  useForceReset2FA,
} from "./hooks/admin/useTwoFactor";
export {
  useAdminSessions,
  useRevokeAdminSession,
  useRevokeOtherAdminSessions,
  useRevokeAllAdminSessions,
  useAdminLoginHistory,
} from "./hooks/admin/useAdminSessions";
