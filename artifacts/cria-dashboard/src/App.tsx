import { Switch, Route, Router as WouterRouter } from "wouter";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import Layout from "@/components/layout/Layout";
import DashboardPage from "@/pages/dashboard";
import ExperimentsPage from "@/pages/experiments";
import ExperimentDetailPage from "@/pages/experiment-detail";
import NewExperimentPage from "@/pages/new-experiment";
import FindingsPage from "@/pages/findings";
import ReflexivityPage from "@/pages/reflexivity";
import TemplatesPage from "@/pages/templates";
import ParallelResearch from "@/pages/parallel-research";
import NotFound from "@/pages/not-found";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, retry: 1 },
  },
});

function Router() {
  return (
    <Layout>
      <Switch>
        <Route path="/research" component={ParallelResearch} />
        <Route path="/" component={DashboardPage} />
        <Route path="/experiments/new" component={NewExperimentPage} />
        <Route path="/experiments/:id" component={ExperimentDetailPage} />
        <Route path="/experiments" component={ExperimentsPage} />
        <Route path="/findings" component={FindingsPage} />
        <Route path="/reflexivity" component={ReflexivityPage} />
        <Route path="/templates" component={TemplatesPage} />
        <Route component={NotFound} />
      </Switch>
    </Layout>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <WouterRouter base={import.meta.env.BASE_URL.replace(/\/$/, "")}>
          <Router />
        </WouterRouter>
        <Toaster />
      </TooltipProvider>
    </QueryClientProvider>
  );
}

export default App;
