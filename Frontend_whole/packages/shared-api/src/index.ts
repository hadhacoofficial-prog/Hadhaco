// API client
export { api } from "./lib/api/client";
export type { RequestOptions, ApiClient } from "./lib/api/client";
export { ApiError, isApiError, toUserMessage } from "./lib/api/errors";
export type { ApiErrorKind } from "./lib/api/errors";
export { queryKeys } from "./lib/api/queryKeys";
export { ENV, hasSupabase, hasApi } from "./config/env";

// Supabase client
export { supabase } from "./lib/supabase/client";

// Supabase auth actions
export {
  signInWithPassword,
  signUpWithPassword,
  signInWithGoogle,
  signOut,
  resetPasswordForEmail,
  updatePassword,
  onAuthStateChange,
} from "./lib/supabase/auth";
export type { AuthResult } from "./lib/supabase/auth";

// Supabase session helpers
export { getSession, getAccessToken, getUserId } from "./lib/supabase/session";

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
