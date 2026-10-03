import { useId } from "react";
import { SignInForm } from "./SignInForm";

/** Shown instead of the tree to visitors who are not signed in, until they
 * enter a code or (if the admin allows guests) choose the public tree. */
export function WelcomeScreen() {
  const titleId = useId();
  return (
    <div className="app">
      <header className="header">
        <h1 className="header__title">FamTree</h1>
      </header>
      <main className="main welcome-page">
        <section className="welcome" aria-labelledby={titleId}>
          <h2 id={titleId}>Welcome</h2>
          <p>Enter the access code you were given to open the family tree.</p>
          <SignInForm offerGuest />
        </section>
      </main>
    </div>
  );
}
