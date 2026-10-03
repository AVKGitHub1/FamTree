import { useId, useRef, useState } from "react";
import { ApiError } from "../../api/client";
import { useSession } from "../../state/session";

/** Asks for an access code; admins switch to the password with a separate
 * button. Codes and the admin password are posted once and exchanged for a
 * session cookie; they never appear in URLs. */
export function SignInForm({ onSignedIn, offerGuest = false }: { onSignedIn?: () => void; offerGuest?: boolean }) {
  const { signIn, continueAsGuest } = useSession();
  const inputId = useId();
  const input = useRef<HTMLInputElement>(null);
  const [kind, setKind] = useState<"code" | "admin">("code");
  const [secret, setSecret] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const switchKind = () => {
    setKind(kind === "code" ? "admin" : "code");
    setSecret("");
    setError(null);
    input.current?.focus();
  };

  const submit = async () => {
    if (!secret.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await signIn(kind, secret.trim());
      onSignedIn?.();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not sign in.");
      setBusy(false);
    }
  };

  return (
    <form
      className="signin"
      onSubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
    >
      <div className="field">
        <label htmlFor={inputId}>{kind === "code" ? "Access code" : "Admin password"}</label>
        <input
          ref={input}
          id={inputId}
          type="password"
          autoComplete={kind === "admin" ? "current-password" : "off"}
          autoFocus
          spellCheck={false}
          value={secret}
          onChange={(e) => setSecret(e.target.value)}
          placeholder={kind === "code" ? "XXXX-XXXX-XXXX-XXXX" : ""}
        />
      </div>
      {error && (
        <p className="error-banner" role="alert">
          {error}
        </p>
      )}
      <button type="submit" className="button button--primary signin__submit" disabled={busy || !secret.trim()}>
        {busy ? "Signing in…" : kind === "code" ? "Sign in" : "Sign in as admin"}
      </button>
      {kind === "code" && continueAsGuest && <p className="hint">Without a code you can see the public parts of the tree.</p>}
      <div className="signin__alternatives">
        {kind === "code" && offerGuest && continueAsGuest && (
          <button type="button" className="button" onClick={continueAsGuest}>
            Continue without a code
          </button>
        )}
        <button type="button" className="button" onClick={switchKind}>
          {kind === "code" ? "Admin sign in" : "Use an access code"}
        </button>
      </div>
    </form>
  );
}
