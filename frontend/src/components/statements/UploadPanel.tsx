import { useEffect, useState } from "react";

import { ApiError, api, type StatementUnlock } from "../../lib/api";
import type {
  Account,
  AccountType,
  Bank,
  Country,
  MappingRequiredDetails,
  Statement,
} from "../../types/api";
import { MappingForm } from "./MappingForm";

const OTHER = "__other";
const NEW = "__new";

const fieldClass =
  "mt-1 w-full rounded border border-slate-300 bg-white px-2 py-1 dark:border-slate-700 dark:bg-slate-900";

type Message = { kind: "success" | "error"; text: string };

function importedText(statement: Statement): string {
  const duplicates =
    statement.duplicate_count > 0
      ? `, ${statement.duplicate_count} already imported from another statement`
      : "";
  return `Imported ${statement.imported_count} transactions from ${statement.filename}${duplicates}.`;
}

export function UploadPanel({ onImported }: { onImported: () => void }) {
  const [banks, setBanks] = useState<Bank[]>([]);
  const [bankId, setBankId] = useState("");
  const [otherName, setOtherName] = useState("");
  const [otherCountry, setOtherCountry] = useState<Country>("US");
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [accountId, setAccountId] = useState("");
  const [newAccountType, setNewAccountType] = useState<AccountType>("bank");
  const [newAccountName, setNewAccountName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [mappingDetails, setMappingDetails] = useState<MappingRequiredDetails | null>(null);
  // Held in memory for this upload only; never written to browser storage.
  const [passwordNeeded, setPasswordNeeded] = useState(false);
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(true);
  const [unlock, setUnlock] = useState<StatementUnlock | undefined>(undefined);
  const [message, setMessage] = useState<Message | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .listBanks()
      .then(setBanks)
      .catch(() => setMessage({ kind: "error", text: "Could not load banks" }));
  }, []);

  const realBankSelected = bankId !== "" && bankId !== OTHER;
  useEffect(() => {
    if (!realBankSelected) return;
    let cancelled = false;
    api
      .listAccounts(bankId)
      .then((loaded) => {
        if (cancelled) return;
        setAccounts(loaded);
        setAccountId(loaded.length === 1 ? String(loaded[0].id) : loaded.length ? "" : NEW);
      })
      .catch(() => !cancelled && setMessage({ kind: "error", text: "Could not load accounts" }));
    return () => {
      cancelled = true;
    };
  }, [bankId, realBankSelected]);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setMessage(null);
    try {
      await action();
    } catch (caught) {
      setMessage({ kind: "error", text: caught instanceof ApiError ? caught.message : "Request failed" });
    } finally {
      setBusy(false);
    }
  }

  const addBank = () =>
    run(async () => {
      const bank = await api.createBank(otherName.trim(), otherCountry);
      setBanks((current) => [...current, bank]);
      setBankId(bank.id);
      setOtherName("");
    });

  const addAccount = () =>
    run(async () => {
      const account = await api.createAccount(bankId, newAccountType, newAccountName.trim());
      setAccounts((current) => [...current, account]);
      setAccountId(String(account.id));
      setNewAccountName("");
    });

  function resetFile() {
    setMappingDetails(null);
    setPasswordNeeded(false);
    setPassword("");
    setUnlock(undefined);
  }

  function finishImport(statement: Statement) {
    resetFile();
    setMessage({ kind: "success", text: importedText(statement) });
    onImported();
  }

  const upload = (withUnlock?: StatementUnlock) =>
    run(async () => {
      if (!file) return;
      try {
        finishImport(await api.uploadStatement(file, Number(accountId), undefined, withUnlock));
      } catch (caught) {
        if (caught instanceof ApiError && caught.code === "csv_mapping_required") {
          setPasswordNeeded(false);
          setUnlock(withUnlock);
          setMappingDetails(caught.details as MappingRequiredDetails);
          return;
        }
        if (
          caught instanceof ApiError &&
          (caught.code === "pdf_password_required" || caught.code === "pdf_password_invalid")
        ) {
          setPasswordNeeded(true);
          setPassword("");
          if (caught.code === "pdf_password_invalid") {
            setMessage({ kind: "error", text: "That password did not open the PDF. Try again." });
          }
          return;
        }
        if (caught instanceof ApiError && caught.code === "duplicate_statement") {
          const { statement_id } = caught.details as { statement_id: number };
          setMessage({
            kind: "error",
            text: `This file was already imported (statement #${statement_id}). Nothing changed.`,
          });
          return;
        }
        throw caught;
      }
    });

  const accountReady = realBankSelected && accountId !== "" && accountId !== NEW;

  return (
    <section aria-labelledby="upload-heading" className="mt-4 rounded border border-slate-200 p-4 dark:border-slate-800">
      <h2 id="upload-heading" className="text-lg font-semibold">
        Upload a statement
      </h2>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <div>
          <label htmlFor="upload-bank" className="block text-sm font-medium">
            Bank
          </label>
          <select
            id="upload-bank"
            value={bankId}
            onChange={(event) => {
              setBankId(event.target.value);
              setAccounts([]);
              setAccountId("");
              resetFile();
            }}
            className={fieldClass}
          >
            <option value="">Choose a bank</option>
            {banks.map((bank) => (
              <option key={bank.id} value={bank.id}>
                {bank.name} ({bank.country})
              </option>
            ))}
            <option value={OTHER}>Other bank or card</option>
          </select>
        </div>

        {bankId === OTHER && (
          <div className="grid gap-2 sm:col-span-2 sm:grid-cols-3 sm:items-end">
            <div>
              <label htmlFor="upload-other-name" className="block text-sm font-medium">
                Bank name
              </label>
              <input
                id="upload-other-name"
                value={otherName}
                onChange={(event) => setOtherName(event.target.value)}
                className={fieldClass}
              />
            </div>
            <div>
              <label htmlFor="upload-other-country" className="block text-sm font-medium">
                Country
              </label>
              <select
                id="upload-other-country"
                value={otherCountry}
                onChange={(event) => setOtherCountry(event.target.value as Country)}
                className={fieldClass}
              >
                <option value="US">United States (USD)</option>
                <option value="IN">India (INR)</option>
              </select>
            </div>
            <button
              type="button"
              onClick={addBank}
              disabled={!otherName.trim() || busy}
              className="rounded border border-slate-300 px-3 py-1.5 text-sm font-medium disabled:opacity-50 dark:border-slate-700"
            >
              Add bank
            </button>
          </div>
        )}

        {realBankSelected && (
          <div>
            <label htmlFor="upload-account" className="block text-sm font-medium">
              Account
            </label>
            <select
              id="upload-account"
              value={accountId}
              onChange={(event) => {
                setAccountId(event.target.value);
                resetFile();
              }}
              className={fieldClass}
            >
              <option value="">Choose an account</option>
              {accounts.map((account) => (
                <option key={account.id} value={account.id}>
                  {account.name} ({account.type === "credit_card" ? "card" : "bank"})
                </option>
              ))}
              <option value={NEW}>New account</option>
            </select>
          </div>
        )}

        {realBankSelected && accountId === NEW && (
          <div className="grid gap-2 sm:col-span-2 sm:grid-cols-3 sm:items-end">
            <div>
              <label htmlFor="upload-account-name" className="block text-sm font-medium">
                Account name
              </label>
              <input
                id="upload-account-name"
                value={newAccountName}
                onChange={(event) => setNewAccountName(event.target.value)}
                placeholder="Checking 1234"
                aria-describedby="upload-account-name-hint"
                className={fieldClass}
              />
              <p id="upload-account-name-hint" className="mt-1 text-xs text-slate-500">
                Use the last 4 digits only, never the full number.
              </p>
            </div>
            <div>
              <label htmlFor="upload-account-type" className="block text-sm font-medium">
                Type
              </label>
              <select
                id="upload-account-type"
                value={newAccountType}
                onChange={(event) => setNewAccountType(event.target.value as AccountType)}
                className={fieldClass}
              >
                <option value="bank">Bank account</option>
                <option value="credit_card">Credit card</option>
              </select>
            </div>
            <button
              type="button"
              onClick={addAccount}
              disabled={!newAccountName.trim() || busy}
              className="rounded border border-slate-300 px-3 py-1.5 text-sm font-medium disabled:opacity-50 dark:border-slate-700"
            >
              Add account
            </button>
          </div>
        )}

        {accountReady && (
          <div>
            <label htmlFor="upload-file" className="block text-sm font-medium">
              Statement file (CSV or PDF)
            </label>
            <input
              id="upload-file"
              type="file"
              accept=".csv,text/csv,.pdf,application/pdf"
              onChange={(event) => {
                setFile(event.target.files?.[0] ?? null);
                resetFile();
                setMessage(null);
              }}
              className="mt-1 w-full text-sm"
            />
          </div>
        )}
      </div>

      {accountReady && passwordNeeded && (
        <form
          className="mt-4 grid gap-2 sm:grid-cols-3 sm:items-end"
          onSubmit={(event) => {
            event.preventDefault();
            upload({ password, remember });
          }}
        >
          <div>
            <label htmlFor="upload-password" className="block text-sm font-medium">
              PDF password
            </label>
            <input
              id="upload-password"
              type="password"
              autoComplete="off"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className={fieldClass}
            />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={remember}
              onChange={(event) => setRemember(event.target.checked)}
            />
            Remember for this bank (macOS Keychain)
          </label>
          <button
            type="submit"
            disabled={!password || busy}
            className="rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
          >
            Unlock and upload
          </button>
        </form>
      )}

      {accountReady && !passwordNeeded && (
        <button
          type="button"
          onClick={() => upload()}
          disabled={!file || busy}
          className="mt-4 rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
        >
          Upload
        </button>
      )}

      {message && (
        <p
          role={message.kind === "error" ? "alert" : "status"}
          className={`mt-3 text-sm ${message.kind === "error" ? "text-red-700 dark:text-red-400" : "text-emerald-700 dark:text-emerald-400"}`}
        >
          {message.text}
        </p>
      )}

      {file && mappingDetails && (
        <MappingForm
          file={file}
          accountId={Number(accountId)}
          details={mappingDetails}
          unlock={unlock}
          onImported={finishImport}
          onCancel={() => setMappingDetails(null)}
        />
      )}
    </section>
  );
}
