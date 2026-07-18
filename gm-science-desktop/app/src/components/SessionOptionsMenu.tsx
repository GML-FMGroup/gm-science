import type { GmScienceSessionPolicy, UpdateGmScienceSessionPolicyInput } from "../types";

interface SessionOptionsMenuProps {
  policy: GmScienceSessionPolicy | null;
  loading: boolean;
  saving: boolean;
  error: string | null;
  onChange: (input: UpdateGmScienceSessionPolicyInput) => void;
}

interface ToggleRowProps {
  label: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (checked: boolean) => void;
}

function ToggleRow({ label, checked, disabled = false, onChange }: ToggleRowProps) {
  return (
    <label className="session-option-row session-option-toggle">
      <span>{label}</span>
      <input
        type="checkbox"
        role="switch"
        aria-label={label}
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
      />
    </label>
  );
}

/** Render the Session-scoped runtime policy controls used by the message composer. */
export function SessionOptionsMenu({ policy, loading, saving, error, onChange }: SessionOptionsMenuProps) {
  const disabled = loading || saving || !policy;

  return (
    <div className="session-options-menu" role="menu" aria-label="Session options">
      {loading && !policy ? <div className="session-options-state">Loading...</div> : null}
      {policy ? (
        <>
          <ToggleRow
            label="Delegation"
            checked={policy.delegationEnabled}
            disabled={disabled}
            onChange={(delegationEnabled) => onChange({ delegationEnabled })}
          />
          <ToggleRow
            label="Auto-review"
            checked={policy.autoReviewEnabled}
            disabled={disabled || !policy.reviewerAvailable}
            onChange={(autoReviewEnabled) => onChange({ autoReviewEnabled })}
          />
          <label className="session-option-row">
            <span>Reviewer model</span>
            <select
              aria-label="Reviewer model"
              value={policy.reviewerModel}
              disabled={disabled}
              onChange={(event) => onChange({ reviewerModel: event.target.value as "default" })}
            >
              {policy.reviewerModels.map((option) => (
                <option key={option.id} value={option.id}>{option.name}</option>
              ))}
            </select>
          </label>
          <ToggleRow
            label="Memory"
            checked={policy.memoryEnabled}
            disabled={disabled}
            onChange={(memoryEnabled) => onChange({ memoryEnabled })}
          />
          <label className="session-option-row">
            <span>Specialist</span>
            <select
              aria-label="Specialist"
              value={policy.specialistId}
              disabled={disabled}
              onChange={(event) => onChange({ specialistId: event.target.value })}
            >
              <option value="">None</option>
              {policy.specialists.map((specialist) => (
                <option key={specialist.id} value={specialist.id}>{specialist.name}</option>
              ))}
            </select>
          </label>
          <label className="session-option-row">
            <span>Compute</span>
            <select
              aria-label="Compute"
              value={policy.computeTarget}
              disabled={disabled}
              onChange={(event) => onChange({ computeTarget: event.target.value as "local" })}
            >
              {policy.computeTargets.map((option) => (
                <option key={option.id} value={option.id}>{option.name}</option>
              ))}
            </select>
          </label>
        </>
      ) : null}
      {error ? <div className="session-options-error" role="alert">{error}</div> : null}
    </div>
  );
}
