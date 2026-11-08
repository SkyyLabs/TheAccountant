import { useEffect, useState } from "react";

import { api } from "../lib/api";

type Status = "checking" | "online" | "offline";

const LABELS: Record<Status, string> = {
  checking: "Checking backend…",
  online: "Backend online",
  offline: "Backend offline: run make run",
};

export function BackendStatus() {
  const [status, setStatus] = useState<Status>("checking");

  useEffect(() => {
    let cancelled = false;
    api
      .health()
      .then(() => !cancelled && setStatus("online"))
      .catch(() => !cancelled && setStatus("offline"));
    return () => {
      cancelled = true;
    };
  }, []);

  // Text plus a dot: never colour alone.
  const dot =
    status === "online" ? "bg-emerald-500" : status === "offline" ? "bg-red-500" : "bg-slate-400";
  return (
    <span role="status" className="flex items-center gap-2 text-sm">
      <span aria-hidden="true" className={`h-2 w-2 rounded-full ${dot}`} />
      {LABELS[status]}
    </span>
  );
}
