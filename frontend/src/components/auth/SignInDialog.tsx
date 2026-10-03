import { Dialog } from "../ui/Dialog";
import { SignInForm } from "./SignInForm";

export function SignInDialog({ onClose }: { onClose: () => void }) {
  return (
    <Dialog title="Sign in" onClose={onClose}>
      <SignInForm onSignedIn={onClose} />
    </Dialog>
  );
}
