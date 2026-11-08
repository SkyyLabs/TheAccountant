import { useCallback, useEffect, useState } from "react";

import { ApiError, api } from "../lib/api";
import type { Category, MatchType, Region, Rule } from "../types/api";

const REGION_LABEL: Record<Region, string> = { both: "US and India", US: "US", IN: "India" };

const fieldClass = "field mt-1";
const buttonClass = "button-primary";

function errorText(caught: unknown, fallback: string): string {
  return caught instanceof ApiError ? caught.message : fallback;
}

export function CategoriesPage() {
  const [categories, setCategories] = useState<Category[]>([]);
  const [rules, setRules] = useState<Rule[]>([]);
  const [message, setMessage] = useState<{ kind: "error" | "success"; text: string } | null>(null);
  const [newName, setNewName] = useState("");
  const [newRegion, setNewRegion] = useState<Region>("both");
  const [renaming, setRenaming] = useState<{ id: number; name: string } | null>(null);
  const [matchType, setMatchType] = useState<MatchType>("contains");
  const [pattern, setPattern] = useState("");
  const [ruleCategoryId, setRuleCategoryId] = useState("");
  const [priority, setPriority] = useState(0);

  const load = useCallback(() => {
    Promise.all([api.listCategories(), api.listRules()])
      .then(([loadedCategories, loadedRules]) => {
        setCategories(loadedCategories);
        setRules(loadedRules);
      })
      .catch(() => setMessage({ kind: "error", text: "Could not load categories and rules" }));
  }, []);

  useEffect(load, [load]);

  async function run(action: () => Promise<string>, fallback: string) {
    setMessage(null);
    try {
      setMessage({ kind: "success", text: await action() });
      load();
    } catch (caught) {
      setMessage({ kind: "error", text: errorText(caught, fallback) });
    }
  }

  const addCategory = () =>
    run(async () => {
      const category = await api.createCategory(newName.trim(), newRegion);
      setNewName("");
      return `Added ${category.name}.`;
    }, "Could not add the category");

  const saveRename = () =>
    run(async () => {
      if (!renaming) return "";
      const category = await api.renameCategory(renaming.id, renaming.name.trim());
      setRenaming(null);
      return `Renamed to ${category.name}.`;
    }, "Could not rename the category");

  const toggleSpending = (category: Category, excluded: boolean) =>
    run(async () => {
      const updated = await api.setExcludedFromSpending(category.id, excluded);
      return updated.excluded_from_spending
        ? `${updated.name} is now left out of spending totals.`
        : `${updated.name} now counts as spending.`;
    }, "Could not change the category");

  const removeCategory = (category: Category) =>
    run(async () => {
      await api.deleteCategory(category.id);
      return `Deleted ${category.name}.`;
    }, "Could not delete the category");

  const addRule = () =>
    run(async () => {
      const { rule, applied_count } = await api.createRule({
        match_type: matchType,
        pattern,
        category_id: Number(ruleCategoryId),
        priority,
      });
      setPattern("");
      return `Rule added for “${rule.pattern}”. ${applied_count} existing transaction${applied_count === 1 ? "" : "s"} moved to ${rule.category_name}.`;
    }, "Could not add the rule");

  const removeRule = (rule: Rule) =>
    run(async () => {
      await api.deleteRule(rule.id);
      return `Deleted the rule for “${rule.pattern}”.`;
    }, "Could not delete the rule");

  return (
    <div className="animate-rise space-y-6">
      <section>
      <p className="text-sm text-muted-foreground">Settings</p>
      <h1 className="mt-1 text-3xl font-semibold tracking-tight">Categories & rules</h1>
      <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
        Rules run before the local model: a transaction whose merchant matches a rule gets its
        category without asking the model. Rules never change a category you set by hand.
      </p>

      {message && (
        <p
          role={message.kind === "error" ? "alert" : "status"}
          className={`mt-3 text-sm ${message.kind === "error" ? "text-destructive" : "text-success"}`}
        >
          {message.text}
        </p>
      )}

      </section>
      <section className="card p-6">
      <h2 className="font-medium">Rules</h2>
      <form
        className="mt-2 grid gap-2 sm:grid-cols-5 sm:items-end"
        onSubmit={(event) => {
          event.preventDefault();
          addRule();
        }}
      >
        <div>
          <label htmlFor="rule-match" className="block text-sm font-medium text-muted-foreground">
            Match
          </label>
          <select
            id="rule-match"
            value={matchType}
            onChange={(event) => setMatchType(event.target.value as MatchType)}
            className={fieldClass}
          >
            <option value="contains">Merchant contains</option>
            <option value="exact">Merchant is exactly</option>
          </select>
        </div>
        <div>
          <label htmlFor="rule-pattern" className="block text-sm font-medium text-muted-foreground">
            Merchant text
          </label>
          <input
            id="rule-pattern"
            value={pattern}
            onChange={(event) => setPattern(event.target.value)}
            placeholder="swiggy"
            className={fieldClass}
          />
        </div>
        <div>
          <label htmlFor="rule-category" className="block text-sm font-medium text-muted-foreground">
            Category
          </label>
          <select
            id="rule-category"
            value={ruleCategoryId}
            onChange={(event) => setRuleCategoryId(event.target.value)}
            className={fieldClass}
          >
            <option value="">Choose a category</option>
            {categories.map((category) => (
              <option key={category.id} value={category.id}>
                {category.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="rule-priority" className="block text-sm font-medium text-muted-foreground">
            Priority (higher first)
          </label>
          <input
            id="rule-priority"
            type="number"
            value={priority}
            onChange={(event) => setPriority(Number(event.target.value))}
            className={fieldClass}
          />
        </div>
        <button type="submit" disabled={!pattern.trim() || !ruleCategoryId} className={buttonClass}>
          Add rule
        </button>
      </form>
      {rules.length === 0 ? (
        <p className="mt-4 text-sm text-muted-foreground">
          No rules yet. Correct a category in Transactions to be offered one.
        </p>
      ) : (
        <table className="mt-3 w-full text-sm">
          <thead>
            <tr className="text-left text-muted-foreground">
              <th scope="col" className="py-1 pr-3 font-medium">Merchant</th>
              <th scope="col" className="py-1 pr-3 font-medium">Category</th>
              <th scope="col" className="py-1 pr-3 font-medium">Priority</th>
              <th scope="col" className="py-1 font-medium">
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rules.map((rule) => (
              <tr key={rule.id} className="border-t">
                <td className="py-1 pr-3">
                  {rule.match_type === "exact" ? "is" : "contains"} “{rule.pattern}”
                </td>
                <td className="py-1 pr-3">{rule.category_name}</td>
                <td className="py-1 pr-3">{rule.priority}</td>
                <td className="py-1">
                  <button
                    type="button"
                    onClick={() => removeRule(rule)}
                    aria-label={`Delete the rule for ${rule.pattern}`}
                    className="text-sm text-destructive"
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      </section>
      <section className="card p-6">
      <h2 className="font-medium">Categories</h2>
      <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
        Tick “Not spending” for money moving between your own accounts (transfers, card
        payments). The Overview leaves those out so nothing is counted twice.
      </p>
      <form
        className="mt-2 grid gap-2 sm:grid-cols-3 sm:items-end"
        onSubmit={(event) => {
          event.preventDefault();
          addCategory();
        }}
      >
        <div>
          <label htmlFor="category-name" className="block text-sm font-medium text-muted-foreground">
            New category
          </label>
          <input
            id="category-name"
            value={newName}
            onChange={(event) => setNewName(event.target.value)}
            className={fieldClass}
          />
        </div>
        <div>
          <label htmlFor="category-region" className="block text-sm font-medium text-muted-foreground">
            Used for
          </label>
          <select
            id="category-region"
            value={newRegion}
            onChange={(event) => setNewRegion(event.target.value as Region)}
            className={fieldClass}
          >
            <option value="both">US and India</option>
            <option value="US">US banks</option>
            <option value="IN">Indian banks</option>
          </select>
        </div>
        <button type="submit" disabled={!newName.trim()} className={buttonClass}>
          Add category
        </button>
      </form>
      <ul className="mt-3 divide-y text-sm">
        {categories.map((category) => (
          <li key={category.id} className="flex flex-wrap items-center gap-3 py-1.5">
            {renaming?.id === category.id ? (
              <form
                className="flex gap-2"
                onSubmit={(event) => {
                  event.preventDefault();
                  saveRename();
                }}
              >
                <input
                  aria-label={`New name for ${category.name}`}
                  value={renaming.name}
                  onChange={(event) => setRenaming({ id: category.id, name: event.target.value })}
                  className="field py-1"
                />
                <button type="submit" className={buttonClass}>
                  Save
                </button>
                <button type="button" onClick={() => setRenaming(null)} className="button-quiet">
                  Cancel
                </button>
              </form>
            ) : (
              <span className="min-w-40 font-medium">{category.name}</span>
            )}
            <span className="text-muted-foreground">{REGION_LABEL[category.region]}</span>
            {category.name !== "Uncategorized" && (
              <label className="flex items-center gap-1 text-muted-foreground">
                <input
                  type="checkbox"
                  checked={category.excluded_from_spending}
                  onChange={(event) => toggleSpending(category, event.target.checked)}
                />
                Not spending
              </label>
            )}
            {category.name !== "Uncategorized" && renaming?.id !== category.id && (
              <>
                <button
                  type="button"
                  onClick={() => setRenaming({ id: category.id, name: category.name })}
                  aria-label={`Rename ${category.name}`}
                  className="text-primary"
                >
                  Rename
                </button>
                <button
                  type="button"
                  onClick={() => removeCategory(category)}
                  aria-label={`Delete ${category.name}`}
                  className="text-destructive"
                >
                  Delete
                </button>
              </>
            )}
          </li>
        ))}
      </ul>
      </section>
    </div>
  );
}
