import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  Outlet,
  Link,
  createRootRouteWithContext,
  useRouter,
  HeadContent,
  Scripts,
} from "@tanstack/react-router";
import { useEffect, type ReactNode } from "react";
import { CartDrawer } from "../components/site/CartDrawer";
import { GlobalJewelleryBackground } from "../components/site/GlobalJewelleryBackground";

import appCss from "../styles.css?url";
import { reportLovableError } from "../lib/lovable-error-reporting";
import markAsset from "../assets/hadha-mark.png";
import { AuthProvider } from "../providers/AuthProvider";
import { RouteTransition } from "../components/common/RouteTransition";
import { ScrollProgress } from "../components/common/ScrollProgress";
import { WhatsAppFab } from "../components/common/WhatsAppFab";
import { MobileBottomNav } from "../components/common/MobileBottomNav";
import { SearchOverlay } from "../components/common/SearchOverlay";
import { WelcomeOfferModal } from "../components/common/WelcomeOfferModal";
import { Toaster } from "../components/ui/sonner";
import { PageLoader } from "../components/common/PageLoader";
import { useProfile } from "../hooks/auth/useProfile";
import { useAuthContext } from "../providers/auth-context";

function NotFoundComponent() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="max-w-md text-center">
        <h1 className="text-7xl font-bold text-foreground">404</h1>
        <h2 className="mt-4 text-xl font-semibold text-foreground">Page not found</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          The page you're looking for doesn't exist or has been moved.
        </p>
        <div className="mt-6">
          <Link
            to="/"
            className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            Go home
          </Link>
        </div>
      </div>
    </div>
  );
}

function ErrorComponent({ error, reset }: { error: Error; reset: () => void }) {
  console.error(error);
  const router = useRouter();
  useEffect(() => {
    reportLovableError(error, { boundary: "tanstack_root_error_component" });
  }, [error]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="max-w-md text-center">
        <h1 className="text-xl font-semibold tracking-tight text-foreground">
          This page didn't load
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Something went wrong on our end. You can try refreshing or head back home.
        </p>
        <div className="mt-6 flex flex-wrap justify-center gap-2">
          <button
            onClick={() => {
              router.invalidate();
              reset();
            }}
            className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            Try again
          </button>
          <a
            href="/"
            className="inline-flex items-center justify-center rounded-md border border-input bg-background px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-accent"
          >
            Go home
          </a>
        </div>
      </div>
    </div>
  );
}

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  head: () => ({
    meta: [
      { charSet: "utf-8" },
      { name: "viewport", content: "width=device-width, initial-scale=1" },
      { title: "Hadha Silver Jewellery | 92.5 Silver Jewellery Collections" },
      {
        name: "description",
        content:
          "Premium 92.5 Silver Jewellery for Women, Men, Kids, Gifts and Accessories. Handcrafted with South Indian heritage.",
      },
      { name: "author", content: "Hadha Silver Jewellery" },
      { name: "theme-color", content: "#A8C8E8" },
      { property: "og:site_name", content: "Hadha Silver Jewellery" },
      { property: "og:title", content: "Hadha Silver Jewellery | 92.5 Silver Jewellery" },
      {
        property: "og:description",
        content: "Premium 92.5 Silver Jewellery — handcrafted, traditional, timeless.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
    links: [
      { rel: "stylesheet", href: appCss },
      { rel: "icon", type: "image/png", href: markAsset },
      { rel: "apple-touch-icon", href: markAsset },
      { rel: "preconnect", href: "https://fonts.googleapis.com" },
      { rel: "preconnect", href: "https://fonts.gstatic.com", crossOrigin: "anonymous" },
      {
        rel: "stylesheet",
        href: "https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;500;600;700&family=Inter:wght@400;500;600&family=Noto+Serif:wght@400;600&display=swap",
      },
    ],
  }),
  shellComponent: RootShell,
  component: RootComponent,
  notFoundComponent: NotFoundComponent,
  errorComponent: ErrorComponent,
});

function RootShell({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <head>
        <HeadContent />
      </head>
      <body>
        {children}
        <Scripts />
      </body>
    </html>
  );
}

function RootComponent() {
  const { queryClient } = Route.useRouteContext();

  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        {/* Toaster is always mounted so alerts can appear even during auth loading. */}
        <Toaster />
        <AppContent />
      </AuthProvider>
    </QueryClientProvider>
  );
}

/**
 * Waits for auth to initialize before rendering any route content.
 *
 * Why: AuthProvider starts with status="loading". Until the initial getSession()
 * resolves, isAuthenticated is false. Component-level route guards that check
 * isAuthenticated would redirect to /account/login before the session is restored,
 * causing a visible flash and a redirect loop on page refresh.
 *
 * Once initialized=true (milliseconds after mount — localStorage read), all
 * route components render with the correct, settled auth state.
 */
function AppContent() {
  const { initialized } = useAuthContext();

  if (!initialized) {
    return <PageLoader logoSrc={markAsset} />;
  }

  return (
    <>
      <GlobalJewelleryBackground />
      <ProfileSyncer />
      <RouteTransition logoSrc={markAsset}>
        <ScrollProgress />
        {/* Required: nested routes render here. */}
        <Outlet />
        <WhatsAppFab />
        <MobileBottomNav />
        <SearchOverlay />
        <WelcomeOfferModal />
      </RouteTransition>
      {/* Mounted once globally so it never unmounts during route transitions */}
      <CartDrawer />
    </>
  );
}

/** Fetches the backend profile once authenticated, setting the authoritative role. */
function ProfileSyncer() {
  useProfile();
  return null;
}
