import { useState, type FormEvent } from "react";

/** Standalone sign-in page (no layout). The real login with a session cookie comes in T2-15. */
export function LoginPage() {
  const [notice, setNotice] = useState<string | null>(null);

  // The fields are uncontrolled and never read: no password is logged or stored anywhere.
  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setNotice("Login is not implemented yet (T2-15).");
  };

  return (
    <main className="login">
      <h1>Sign in to ICD</h1>
      <p>Analysts sign in here before they can see incidents or make response decisions.</p>
      <form className="login__form" onSubmit={onSubmit}>
        <label>
          Username
          <input name="username" type="text" autoComplete="username" />
        </label>
        <label>
          Password
          <input name="password" type="password" autoComplete="current-password" />
        </label>
        <button type="submit">Sign in</button>
      </form>
      {notice && <p role="status">{notice}</p>}
    </main>
  );
}
