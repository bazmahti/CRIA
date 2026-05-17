import { useEffect, useRef } from "react";
import { ClerkProvider, SignIn, SignUp, Show, useClerk } from "@clerk/react";
import { publishableKeyFromHost } from "@clerk/react/internal";
import { shadcn } from "@clerk/themes";
import { Switch, Route, Router as WouterRouter, useLocation, Redirect } from "wouter";
import { QueryClient, QueryClientProvider, useQueryClient } from "@tanstack/react-query";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import Layout from "@/components/layout/Layout";
import DashboardPage from "@/pages/dashboard";
import ExperimentsPage from "@/pages/experiments";
import ExperimentDetailPage from "@/pages/experiment-detail";
import NewExperimentPage from "@/pages/new-experiment";
import FindingsPage from "@/pages/findings";
import ReflexivityPage from "@/pages/reflexivity";
import HorizonPage from "@/pages/horizon";
import TemplatesPage from "@/pages/templates";
import ParallelResearch from "@/pages/parallel-research";
import UnifiedResearch from "@/pages/unified-research";
import ResearchHistoryPage from "@/pages/research-history";
import SearchPage from "@/pages/search";
import NotFound from "@/pages/not-found";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, retry: 1 },
  },
});

const clerkPubKey = publishableKeyFromHost(
  window.location.hostname,
  import.meta.env.VITE_CLERK_PUBLISHABLE_KEY,
);

const clerkProxyUrl = import.meta.env.VITE_CLERK_PROXY_URL;

const basePath = import.meta.env.BASE_URL.replace(/\/$/, "");

function stripBase(path: string): string {
  return basePath && path.startsWith(basePath)
    ? path.slice(basePath.length) || "/"
    : path;
}

if (!clerkPubKey) {
  throw new Error("Missing VITE_CLERK_PUBLISHABLE_KEY");
}

const clerkAppearance = {
  theme: shadcn,
  cssLayerName: "clerk",
  options: {
    logoPlacement: "inside" as const,
    logoLinkUrl: basePath || "/",
    logoImageUrl: `${window.location.origin}${basePath}/logo.svg`,
    socialButtonsPlacement: "top" as const,
    socialButtonsVariant: "blockButton" as const,
  },
  variables: {
    colorPrimary: "hsl(217 91% 60%)",
    colorForeground: "hsl(210 40% 98%)",
    colorMutedForeground: "hsl(215 20% 55%)",
    colorDanger: "hsl(0 72% 51%)",
    colorBackground: "hsl(222 47% 11%)",
    colorInput: "hsl(217 32% 20%)",
    colorInputForeground: "hsl(210 40% 98%)",
    colorNeutral: "hsl(217 32% 18%)",
    fontFamily: "'Inter', sans-serif",
    borderRadius: "0.5rem",
  },
  elements: {
    rootBox: "w-full flex justify-center",
    cardBox: "bg-[hsl(222,47%,13%)] border border-[hsl(217,32%,18%)] rounded-2xl w-[440px] max-w-full overflow-hidden shadow-2xl",
    card: "!shadow-none !border-0 !bg-transparent !rounded-none",
    footer: "!shadow-none !border-0 !bg-transparent !rounded-none",
    headerTitle: "text-[hsl(210,40%,98%)] font-semibold",
    headerSubtitle: "text-[hsl(215,20%,55%)]",
    socialButtonsBlockButtonText: "text-[hsl(210,40%,98%)]",
    formFieldLabel: "text-[hsl(210,40%,98%)]",
    footerActionLink: "text-[hsl(217,91%,60%)] hover:text-[hsl(217,91%,70%)]",
    footerActionText: "text-[hsl(215,20%,55%)]",
    dividerText: "text-[hsl(215,20%,55%)]",
    identityPreviewEditButton: "text-[hsl(217,91%,60%)]",
    formFieldSuccessText: "text-[hsl(160,60%,50%)]",
    alertText: "text-[hsl(210,40%,98%)]",
    logoBox: "mb-1",
    logoImage: "h-10 w-10",
    socialButtonsBlockButton: "border-[hsl(217,32%,25%)] hover:bg-[hsl(217,32%,17%)]",
    formButtonPrimary: "bg-[hsl(217,91%,60%)] hover:bg-[hsl(217,91%,55%)] text-[hsl(222,47%,11%)]",
    formFieldInput: "bg-[hsl(217,32%,20%)] border-[hsl(217,32%,25%)] text-[hsl(210,40%,98%)]",
    footerAction: "border-t border-[hsl(217,32%,18%)]",
    dividerLine: "bg-[hsl(217,32%,18%)]",
    alert: "border-[hsl(217,32%,25%)]",
    otpCodeFieldInput: "bg-[hsl(217,32%,20%)] border-[hsl(217,32%,25%)] text-[hsl(210,40%,98%)]",
    formFieldRow: "",
    main: "",
  },
};

function SignInPage() {
  return (
    <div className="flex min-h-[100dvh] items-center justify-center bg-background px-4">
      <div className="w-full max-w-[440px]">
        <div className="text-center mb-6">
          <div className="inline-flex items-center gap-2.5 mb-2">
            <div className="w-8 h-8 rounded bg-primary/20 border border-primary/30 flex items-center justify-center">
              <svg viewBox="0 0 16 16" className="w-4 h-4 text-primary fill-current">
                <circle cx="8" cy="8" r="3" opacity="0.9"/>
                <circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" strokeWidth="1" opacity="0.6"/>
                <line x1="8" y1="1" x2="8" y2="4" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" opacity="0.7"/>
                <line x1="8" y1="12" x2="8" y2="15" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" opacity="0.7"/>
                <line x1="1" y1="8" x2="4" y2="8" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" opacity="0.7"/>
                <line x1="12" y1="8" x2="15" y2="8" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" opacity="0.7"/>
              </svg>
            </div>
            <span className="text-lg font-semibold tracking-tight">CRIA</span>
          </div>
          <p className="text-xs text-muted-foreground font-mono">Convergent Research Intelligence Architecture</p>
        </div>
        <SignIn routing="path" path={`${basePath}/sign-in`} signUpUrl={`${basePath}/sign-up`} />
      </div>
    </div>
  );
}

function SignUpPage() {
  return (
    <div className="flex min-h-[100dvh] items-center justify-center bg-background px-4">
      <div className="w-full max-w-[440px]">
        <div className="text-center mb-6">
          <div className="inline-flex items-center gap-2.5 mb-2">
            <div className="w-8 h-8 rounded bg-primary/20 border border-primary/30 flex items-center justify-center">
              <svg viewBox="0 0 16 16" className="w-4 h-4 text-primary fill-current">
                <circle cx="8" cy="8" r="3" opacity="0.9"/>
                <circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" strokeWidth="1" opacity="0.6"/>
                <line x1="8" y1="1" x2="8" y2="4" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" opacity="0.7"/>
                <line x1="8" y1="12" x2="8" y2="15" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" opacity="0.7"/>
                <line x1="1" y1="8" x2="4" y2="8" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" opacity="0.7"/>
                <line x1="12" y1="8" x2="15" y2="8" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" opacity="0.7"/>
              </svg>
            </div>
            <span className="text-lg font-semibold tracking-tight">CRIA</span>
          </div>
          <p className="text-xs text-muted-foreground font-mono">Convergent Research Intelligence Architecture</p>
        </div>
        <SignUp routing="path" path={`${basePath}/sign-up`} signInUrl={`${basePath}/sign-in`} />
      </div>
    </div>
  );
}

function ClerkQueryClientCacheInvalidator() {
  const { addListener } = useClerk();
  const qc = useQueryClient();
  const prevUserIdRef = useRef<string | null | undefined>(undefined);

  useEffect(() => {
    const unsubscribe = addListener(({ user }) => {
      const userId = user?.id ?? null;
      if (prevUserIdRef.current !== undefined && prevUserIdRef.current !== userId) {
        qc.clear();
      }
      prevUserIdRef.current = userId;
    });
    return unsubscribe;
  }, [addListener, qc]);

  return null;
}

function ProtectedApp() {
  return (
    <Show when="signed-in">
      <Layout>
        <Switch>
          <Route path="/research" component={ParallelResearch} />
          <Route path="/unified" component={UnifiedResearch} />
          <Route path="/control-room" component={DashboardPage} />
          <Route path="/"><Redirect to="/unified" /></Route>
          <Route path="/experiments/new" component={NewExperimentPage} />
          <Route path="/experiments/:id" component={ExperimentDetailPage} />
          <Route path="/experiments" component={ExperimentsPage} />
          <Route path="/history" component={ResearchHistoryPage} />
          <Route path="/search" component={SearchPage} />
          <Route path="/findings" component={FindingsPage} />
          <Route path="/reflexivity" component={ReflexivityPage} />
          <Route path="/horizon" component={HorizonPage} />
          <Route path="/templates" component={TemplatesPage} />
          <Route component={NotFound} />
        </Switch>
      </Layout>
    </Show>
  );
}

function AppRoutes() {
  return (
    <Switch>
      <Route path="/sign-in/*?" component={SignInPage} />
      <Route path="/sign-up/*?" component={SignUpPage} />
      <Route>
        <Show when="signed-in">
          <ProtectedApp />
        </Show>
        <Show when="signed-out">
          <Redirect to="/sign-in" />
        </Show>
      </Route>
    </Switch>
  );
}

function ClerkProviderWithRoutes() {
  const [, setLocation] = useLocation();

  return (
    <ClerkProvider
      publishableKey={clerkPubKey}
      proxyUrl={clerkProxyUrl}
      appearance={clerkAppearance}
      signInUrl={`${basePath}/sign-in`}
      signUpUrl={`${basePath}/sign-up`}
      localization={{
        signIn: {
          start: {
            title: "Sign in to CRIA",
            subtitle: "Your research intelligence platform",
          },
        },
        signUp: {
          start: {
            title: "Create your account",
            subtitle: "Access CRIA research tools",
          },
        },
      }}
      routerPush={(to) => setLocation(stripBase(to))}
      routerReplace={(to) => setLocation(stripBase(to), { replace: true })}
    >
      <QueryClientProvider client={queryClient}>
        <ClerkQueryClientCacheInvalidator />
        <TooltipProvider>
          <AppRoutes />
          <Toaster />
        </TooltipProvider>
      </QueryClientProvider>
    </ClerkProvider>
  );
}

function App() {
  return (
    <WouterRouter base={basePath}>
      <ClerkProviderWithRoutes />
    </WouterRouter>
  );
}

export default App;
