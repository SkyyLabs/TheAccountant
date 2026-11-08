import { NavLink, Navigate, Route, Routes } from "react-router";

import { BackendStatus } from "./components/BackendStatus";
import { CategoriesPage } from "./routes/CategoriesPage";
import { ChatPage } from "./routes/ChatPage";
import { OverviewPage } from "./routes/OverviewPage";
import { StatementsPage } from "./routes/StatementsPage";
import { TransactionsPage } from "./routes/TransactionsPage";

const TABS = [
  { path: "/overview", label: "Overview", element: <OverviewPage /> },
  { path: "/transactions", label: "Transactions", element: <TransactionsPage /> },
  { path: "/statements", label: "Statements", element: <StatementsPage /> },
  { path: "/categories", label: "Categories & Rules", element: <CategoriesPage /> },
  { path: "/chat", label: "Chat", element: <ChatPage /> },
];

export function App() {
  return (
    <div className="min-h-screen bg-white text-slate-900 dark:bg-slate-950 dark:text-slate-100">
      <header className="border-b border-slate-200 dark:border-slate-800">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <span className="text-lg font-semibold">TheAccountant</span>
          <BackendStatus />
        </div>
        <nav aria-label="Main" className="mx-auto max-w-6xl overflow-x-auto px-4">
          <ul className="flex gap-1">
            {TABS.map((tab) => (
              <li key={tab.path}>
                <NavLink
                  to={tab.path}
                  className={({ isActive }) =>
                    `block whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium focus-visible:outline-2 focus-visible:outline-blue-600 ${
                      isActive
                        ? "border-blue-600 text-blue-700 dark:text-blue-400"
                        : "border-transparent text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
                    }`
                  }
                >
                  {tab.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">
        <Routes>
          <Route path="/" element={<Navigate to="/overview" replace />} />
          {TABS.map((tab) => (
            <Route key={tab.path} path={tab.path} element={tab.element} />
          ))}
          <Route path="*" element={<Navigate to="/overview" replace />} />
        </Routes>
      </main>
    </div>
  );
}
