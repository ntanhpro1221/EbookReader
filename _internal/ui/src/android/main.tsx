import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "../styles.css";
import { initAndroidSource } from "./androidSource";
import { AndroidApp } from "./App";

const client = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: true, staleTime: 1000 } },
});

void initAndroidSource().finally(() => {
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <QueryClientProvider client={client}>
        <AndroidApp />
      </QueryClientProvider>
    </StrictMode>,
  );
});
