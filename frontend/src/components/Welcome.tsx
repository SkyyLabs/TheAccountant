import { Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router";

import { api } from "../lib/api";

export const WELCOME_MS = 2500;

/** The first screen: a moment of calm, then upload (first visit) or the dashboard. */
export function Welcome() {
  const navigate = useNavigate();
  const [next, setNext] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(false);

  useEffect(() => {
    api
      .listImports()
      .then((imports) => setNext(imports.some((i) => i.status === "done") ? "/dashboard" : "/upload"))
      .catch(() => setNext("/upload"));
    const timer = setTimeout(() => setElapsed(true), WELCOME_MS);
    return () => clearTimeout(timer);
  }, []);

  // Leave once the welcome has shown long enough and we know where to go.
  useEffect(() => {
    if (elapsed && next) navigate(next, { replace: true });
  }, [elapsed, next, navigate]);

  return (
    <main className="flex min-h-screen items-center justify-center bg-gradient-to-br from-[oklch(0.45_0.24_277)] via-primary to-[oklch(0.6_0.22_300)] text-white">
      <div className="animate-rise text-center">
        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-white/15 ring-1 ring-white/30 backdrop-blur">
          <Sparkles aria-hidden="true" className="h-8 w-8" />
        </div>
        <h1 className="mt-6 text-4xl font-semibold tracking-tight">TheAccountant</h1>
        <p className="mt-3 text-lg text-white/80">Your money, understood. Privately, on this Mac.</p>
      </div>
    </main>
  );
}
