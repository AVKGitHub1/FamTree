import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import * as api from "../../api/endpoints";
import type { AccessCode, CodeRole } from "../../api/types";
import { useToast } from "../../state/toasts";
import { Dialog } from "../ui/Dialog";

const ROLE_OPTIONS: [CodeRole, string, string][] = [
  ["public_viewer", "Public viewer", "Sees only public information, like a guest; still works when guest access is off."],
  ["private_viewer", "Family viewer", "Sees public and private information; cannot edit."],
  ["editor", "Editor", "Sees everything and edits people, relationships and details."],
];

const errorText = (err: unknown) => (err instanceof ApiError ? err.message : "Something went wrong.");

export function AdminDialog({ onClose }: { onClose: () => void }) {
  const [tab, setTab] = useState<"codes" | "guests" | "password">("codes");
  return (
    <Dialog title="Admin" size="wide" onClose={onClose}>
      <div className="tabs" role="tablist" aria-label="Admin sections">
        <button type="button" role="tab" aria-selected={tab === "codes"} onClick={() => setTab("codes")}>
          Access codes
        </button>
        <button type="button" role="tab" aria-selected={tab === "guests"} onClick={() => setTab("guests")}>
          Guest access
        </button>
        <button type="button" role="tab" aria-selected={tab === "password"} onClick={() => setTab("password")}>
          Admin password
        </button>
      </div>
      {tab === "codes" ? <CodesPanel /> : tab === "guests" ? <GuestsPanel /> : <PasswordPanel />}
    </Dialog>
  );
}

function CopyButton({ value }: { value: string }) {
  const notify = useToast();
  return (
    <button
      type="button"
      className="link-button"
      onClick={() =>
        navigator.clipboard?.writeText(value).then(
          () => notify("Copied.", "success"),
          () => notify("Copy failed; select the code and copy it manually.", "error"),
        )
      }
    >
      Copy
    </button>
  );
}

function CodesPanel() {
  const notify = useToast();
  const [codes, setCodes] = useState<AccessCode[] | null>(null);
  const [revealed, setRevealed] = useState<Record<string, string>>({});
  const [label, setLabel] = useState("");
  const [role, setRole] = useState<CodeRole>("private_viewer");
  const [created, setCreated] = useState<{ label: string; value: string } | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  const load = useCallback(
    () => api.listCodes().then((r) => setCodes(r.codes), (err) => notify(errorText(err), "error")),
    [notify],
  );

  useEffect(() => {
    load();
  }, [load]);

  const act = async (action: () => Promise<unknown>, message: string) => {
    try {
      await action();
      await load();
      notify(message, "success");
    } catch (err) {
      notify(errorText(err), "error");
    }
  };

  const create = async () => {
    try {
      const result = await api.createCode(label.trim(), role);
      setCreated({ label: result.code.label, value: result.value });
      setLabel("");
      await load();
    } catch (err) {
      notify(errorText(err), "error");
    }
  };

  return (
    <div className="codes">
      <form
        className="codes__create"
        onSubmit={(event) => {
          event.preventDefault();
          void create();
        }}
      >
        <div className="field">
          <label htmlFor="code-label">Label (who is it for?)</label>
          <input id="code-label" value={label} maxLength={80} onChange={(e) => setLabel(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="code-role">Access</label>
          <select id="code-role" value={role} onChange={(e) => setRole(e.target.value as CodeRole)}>
            {ROLE_OPTIONS.map(([value, text]) => (
              <option key={value} value={value}>
                {text}
              </option>
            ))}
          </select>
        </div>
        <button type="submit" className="button button--primary">
          Create code
        </button>
        <p className="hint">{ROLE_OPTIONS.find(([value]) => value === role)?.[2]}</p>
      </form>

      {created && (
        <div className="created-code" role="status">
          <p>
            New code{created.label ? ` for ${created.label}` : ""}: <code>{created.value}</code> <CopyButton value={created.value} />
          </p>
          <p className="hint">Share it privately. You can reveal it again here later.</p>
        </div>
      )}

      {codes === null ? (
        <p>Loading…</p>
      ) : codes.length === 0 ? (
        <p className="muted">No access codes yet.</p>
      ) : (
        <table className="codes__table">
          <thead>
            <tr>
              <th scope="col">Label</th>
              <th scope="col">Access</th>
              <th scope="col">Created</th>
              <th scope="col">Code</th>
              <th scope="col">
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {codes.map((code) => (
              <tr key={code.id} className={code.revoked ? "is-revoked" : undefined}>
                <td>{code.label || <span className="muted">(no label)</span>}</td>
                <td>
                  <select
                    aria-label={`Access for ${code.label || "this code"}`}
                    value={code.role}
                    onChange={(e) =>
                      act(() => api.updateCode(code.id, { role: e.target.value as CodeRole }), "Access updated.")
                    }
                  >
                    {ROLE_OPTIONS.map(([value, text]) => (
                      <option key={value} value={value}>
                        {text}
                      </option>
                    ))}
                  </select>
                  {code.revoked && <span className="badge badge--private">Revoked</span>}
                </td>
                <td>{new Date(code.created_at).toLocaleDateString()}</td>
                <td>
                  {revealed[code.id] ? (
                    <>
                      <code>{revealed[code.id]}</code> <CopyButton value={revealed[code.id]} />
                    </>
                  ) : (
                    <button
                      type="button"
                      className="link-button"
                      onClick={async () => {
                        try {
                          const { value } = await api.revealCode(code.id);
                          setRevealed((all) => ({ ...all, [code.id]: value }));
                        } catch (err) {
                          notify(errorText(err), "error");
                        }
                      }}
                    >
                      Reveal
                    </button>
                  )}
                </td>
                <td className="codes__actions">
                  <button
                    type="button"
                    className="link-button"
                    onClick={() =>
                      act(
                        () => api.updateCode(code.id, { revoked: !code.revoked }),
                        code.revoked ? "Code reinstated." : "Code revoked; its sessions have ended.",
                      )
                    }
                  >
                    {code.revoked ? "Reinstate" : "Revoke"}
                  </button>
                  {confirmDelete === code.id ? (
                    <>
                      <button
                        type="button"
                        className="link-button link-button--danger"
                        onClick={() => act(() => api.deleteCode(code.id), "Code deleted.").then(() => setConfirmDelete(null))}
                      >
                        Confirm delete
                      </button>
                      <button type="button" className="link-button" onClick={() => setConfirmDelete(null)}>
                        Cancel
                      </button>
                    </>
                  ) : (
                    <button type="button" className="link-button link-button--danger" onClick={() => setConfirmDelete(code.id)}>
                      Delete
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function GuestsPanel() {
  const notify = useToast();
  const [enabled, setEnabled] = useState<boolean | null>(null);

  useEffect(() => {
    api.getSettings().then(
      (settings) => setEnabled(settings.guest_access),
      (err) => notify(errorText(err), "error"),
    );
  }, [notify]);

  const change = async (next: boolean) => {
    const previous = enabled;
    setEnabled(next);
    try {
      setEnabled((await api.updateSettings({ guest_access: next })).guest_access);
      notify(next ? "Guests can see the public tree." : "Visitors now need an access code.", "success");
    } catch (err) {
      setEnabled(previous);
      notify(errorText(err), "error");
    }
  };

  return (
    <fieldset className="choice guest-access">
      <legend>What visitors without an access code see</legend>
      <label>
        <input type="radio" name="guest-access" checked={enabled === true} disabled={enabled === null} onChange={() => change(true)} />
        <span>
          The public tree
          <span className="hint">Names, public details and public relationships. Visitors can skip the code screen.</span>
        </span>
      </label>
      <label>
        <input type="radio" name="guest-access" checked={enabled === false} disabled={enabled === null} onChange={() => change(false)} />
        <span>
          Nothing
          <span className="hint">The site only asks for an access code. Public viewer codes still open the public tree.</span>
        </span>
      </label>
    </fieldset>
  );
}

function PasswordPanel() {
  const notify = useToast();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setError(null);
    if (next !== confirm) return setError("The new passwords do not match.");
    try {
      await api.changePassword(current, next);
      setCurrent("");
      setNext("");
      setConfirm("");
      notify("Password changed. Other admin sessions were signed out.", "success");
    } catch (err) {
      setError(errorText(err));
    }
  };

  return (
    <form
      className="password-form"
      onSubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
    >
      <div className="field">
        <label htmlFor="pw-current">Current password</label>
        <input id="pw-current" type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} />
      </div>
      <div className="field">
        <label htmlFor="pw-new">New password (at least 12 characters)</label>
        <input id="pw-new" type="password" autoComplete="new-password" minLength={12} value={next} onChange={(e) => setNext(e.target.value)} />
      </div>
      <div className="field">
        <label htmlFor="pw-confirm">Repeat new password</label>
        <input id="pw-confirm" type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
      </div>
      {error && (
        <p className="error-banner" role="alert">
          {error}
        </p>
      )}
      <button type="submit" className="button button--primary" disabled={!current || !next}>
        Change password
      </button>
    </form>
  );
}
