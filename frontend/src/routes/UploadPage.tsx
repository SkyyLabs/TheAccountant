import { CheckCircle2, FileText, Loader2, Lock, UploadCloud, XCircle } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";

import { ApiError, api } from "../lib/api";
import type { Import } from "../types/api";

export const POLL_MS = 1500;
export const REDIRECT_MS = 1500;

type Item = {
  key: string;
  file: File;
  state: "uploading" | "processing" | "done" | "failed" | "password" | "duplicate";
  imported?: Import;
  message?: string;
  passwordWrong?: boolean;
};

function describe(item: Item): string {
  if (item.state === "uploading") return "Uploading…";
  if (item.state === "duplicate") return "Already uploaded before";
  if (item.state === "password") return "This PDF is locked. Enter its password.";
  if (item.state === "failed") return item.message ?? "Could not be read";
  const imported = item.imported;
  if (item.state === "done" && imported) {
    const count = imported.statements.reduce((n, s) => n + s.imported_count, 0);
    const accounts = imported.statements.map((s) => `${s.bank_name} ${s.account_name}`).join(", ");
    return `${count} transactions · ${accounts}`;
  }
  if (!imported || imported.progress_total === 0) return "Reading with the local AI…";
  if (imported.progress_done < imported.progress_total) {
    return `Reading with the local AI · part ${imported.progress_done + 1} of ${imported.progress_total}`;
  }
  return "Sorting into categories…";
}

function percent(item: Item): number {
  if (item.state === "done" || item.state === "duplicate") return 100;
  const imported = item.imported;
  if (item.state !== "processing" || !imported || imported.progress_total === 0) return 5;
  // The last 10% is categorizing.
  return 5 + Math.round((85 * imported.progress_done) / imported.progress_total);
}

export function UploadPage() {
  const navigate = useNavigate();
  const [items, setItems] = useState<Item[]>([]);
  const [dragging, setDragging] = useState(false);
  const [passwords, setPasswords] = useState<Record<string, string>>({});
  const [remember, setRemember] = useState(true);
  const input = useRef<HTMLInputElement>(null);

  const update = useCallback((key: string, changes: Partial<Item>) => {
    setItems((current) => current.map((i) => (i.key === key ? { ...i, ...changes } : i)));
  }, []);

  const send = useCallback(
    async (item: Item, password?: string) => {
      update(item.key, { state: "uploading", message: undefined });
      try {
        const imported = await api.uploadImport(item.file, password, remember);
        update(item.key, { state: "processing", imported });
      } catch (caught) {
        const code = caught instanceof ApiError ? caught.code : "";
        if (code === "pdf_password_required" || code === "pdf_password_invalid") {
          update(item.key, { state: "password", passwordWrong: code === "pdf_password_invalid" });
        } else if (code === "duplicate_statement") {
          update(item.key, { state: "duplicate" });
        } else {
          const message = caught instanceof ApiError ? caught.message : "Upload failed";
          update(item.key, { state: "failed", message });
        }
      }
    },
    [remember, update],
  );

  function add(files: FileList | null) {
    if (!files) return;
    const added = Array.from(files).map((file, index) => ({
      key: `${file.name}-${file.size}-${Date.now()}-${index}`,
      file,
      state: "uploading" as const,
    }));
    setItems((current) => [...current, ...added]);
    added.forEach((item) => send(item));
  }

  // Poll every import the local AI is still reading.
  const processing = items.filter((i) => i.state === "processing" && i.imported);
  useEffect(() => {
    if (processing.length === 0) return;
    const timer = setTimeout(() => {
      processing.forEach((item) =>
        api
          .getImport(item.imported!.id)
          .then((imported) =>
            update(item.key, {
              imported,
              state: imported.status === "processing" ? "processing" : imported.status,
              message: imported.error ?? undefined,
            }),
          )
          .catch(() => undefined),
      );
    }, POLL_MS);
    return () => clearTimeout(timer);
  }, [processing, update]);

  const settled =
    items.length > 0 && items.every((i) => ["done", "failed", "duplicate"].includes(i.state));
  const anyRead = items.some((i) => i.state === "done" || i.state === "duplicate");
  useEffect(() => {
    if (!settled || !anyRead) return;
    const timer = setTimeout(() => navigate("/dashboard"), REDIRECT_MS);
    return () => clearTimeout(timer);
  }, [settled, anyRead, navigate]);

  return (
    <div className="mx-auto max-w-3xl animate-rise">
      <p className="text-sm text-muted-foreground">Step 1 of 2</p>
      <h1 className="mt-1 text-3xl font-semibold tracking-tight">Upload your statements</h1>
      <p className="mt-2 text-muted-foreground">
        Any bank or card, PDF or CSV, as many as you like. The AI runs on this Mac: nothing leaves
        it.
      </p>

      <button
        type="button"
        onClick={() => input.current?.click()}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          add(event.dataTransfer.files);
        }}
        className={`mt-8 flex w-full flex-col items-center justify-center rounded-3xl border-2 border-dashed px-6 py-16 text-center transition focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-primary ${
          dragging ? "border-primary bg-accent" : "bg-card hover:border-primary/60 hover:bg-accent/50"
        }`}
      >
        <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-accent text-accent-foreground">
          <UploadCloud aria-hidden="true" className="h-7 w-7" />
        </span>
        <span className="mt-4 text-lg font-medium">Drop statements here</span>
        <span className="mt-1 text-sm text-muted-foreground">or click to choose files · PDF or CSV</span>
      </button>
      <input
        ref={input}
        type="file"
        multiple
        accept=".pdf,.csv,application/pdf,text/csv"
        aria-label="Choose statement files"
        className="sr-only"
        onChange={(event) => {
          add(event.target.files);
          event.target.value = "";
        }}
      />

      {items.length > 0 && (
        <ul className="mt-8 space-y-3">
          {items.map((item) => (
            <li
              key={item.key}
              className="card animate-rise p-5"
            >
              <div className="flex items-center gap-3">
                <FileText aria-hidden="true" className="h-5 w-5 shrink-0 text-muted-foreground" />
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium">{item.file.name}</p>
                  <p
                    className={`truncate text-sm ${item.state === "failed" ? "text-destructive" : "text-muted-foreground"}`}
                  >
                    {describe(item)}
                  </p>
                </div>
                {(item.state === "uploading" || item.state === "processing") && (
                  <Loader2 aria-hidden="true" className="h-5 w-5 animate-spin text-primary" />
                )}
                {(item.state === "done" || item.state === "duplicate") && (
                  <CheckCircle2 aria-hidden="true" className="h-5 w-5 text-success" />
                )}
                {item.state === "failed" && (
                  <XCircle aria-hidden="true" className="h-5 w-5 text-destructive" />
                )}
                {item.state === "password" && (
                  <Lock aria-hidden="true" className="h-5 w-5 text-warning" />
                )}
              </div>
              {item.state !== "password" && item.state !== "failed" && (
                <div
                  role="progressbar"
                  aria-label={`Progress for ${item.file.name}`}
                  aria-valuenow={percent(item)}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  className="mt-4 h-1.5 overflow-hidden rounded-full bg-muted"
                >
                  <div
                    className="h-full rounded-full bg-primary transition-all duration-700"
                    style={{ width: `${percent(item)}%` }}
                  />
                </div>
              )}
              {item.state === "password" && (
                <form
                  className="mt-3 flex flex-wrap items-center gap-3"
                  onSubmit={(event) => {
                    event.preventDefault();
                    send(item, passwords[item.key]);
                  }}
                >
                  <input
                    type="password"
                    autoComplete="off"
                    aria-label={`Password for ${item.file.name}`}
                    value={passwords[item.key] ?? ""}
                    onChange={(event) =>
                      setPasswords((current) => ({ ...current, [item.key]: event.target.value }))
                    }
                    className="field min-w-0 flex-1"
                  />
                  <label className="flex items-center gap-2 text-sm text-muted-foreground">
                    <input
                      type="checkbox"
                      checked={remember}
                      onChange={(event) => setRemember(event.target.checked)}
                    />
                    Remember for this bank
                  </label>
                  <button
                    type="submit"
                    disabled={!passwords[item.key]}
                    className="button-primary"
                  >
                    Unlock
                  </button>
                  {item.passwordWrong && (
                    <p role="alert" className="w-full text-sm text-destructive">
                      That password did not open the PDF.
                    </p>
                  )}
                </form>
              )}
            </li>
          ))}
        </ul>
      )}

      {settled && anyRead && (
        <p role="status" className="mt-6 text-center text-sm text-muted-foreground">
          All set. Opening your dashboard…
        </p>
      )}
    </div>
  );
}
