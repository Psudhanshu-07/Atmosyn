import { VARIABLES } from "../lib/constants";
import { VARIABLE_LABELS } from "../lib/format";
import type { Variable } from "../lib/types";

export function VariableSelector({
  value,
  onChange,
}: {
  value: Variable;
  onChange: (v: Variable) => void;
}) {
  return (
    <label className="inline-flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-slate-500">
      Variable
      <select
        value={value}
        onChange={(e) => onChange(e.target.value as Variable)}
        className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm font-normal normal-case tracking-normal text-slate-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500"
      >
        {VARIABLES.map((v) => (
          <option key={v} value={v}>
            {VARIABLE_LABELS[v]}
          </option>
        ))}
      </select>
    </label>
  );
}
