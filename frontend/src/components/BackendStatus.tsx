import { useEffect, useState } from "react";

import { api } from "../lib/api";

type Status = "checking" | "online" | "offline";

const LABELS: Record<Status, string> = {
  checking: "Connecting…",
  online: "Private · offline",
  offline: "App server is not running",
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
    status === "online" ? "bg-success" : status === "offline" ? "bg-destructive" : "bg-muted-foreground";
  return (
    <span role="status" className="hidden items-center gap-2 text-xs text-muted-foreground sm:flex">
      <span aria-hidden="true" className={`h-2 w-2 rounded-full ${dot}`} />
      {LABELS[status]}
    </span>
  );
}
