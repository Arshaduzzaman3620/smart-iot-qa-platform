import { useEffect, useRef } from "react";

interface Props {
  open: boolean;
  title: string;
  message: string;
  confirmLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
}

/** "Are you sure?" for actions that disrupt something (restart a device, delete a user). A native
 *  <dialog>: focus stays inside, Escape cancels, and the page behind can't be clicked. */
export function ConfirmDialog({ open, title, message, confirmLabel, onConfirm, onCancel }: Props) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog ref={ref} className="dialog" aria-labelledby="dialog-title" data-testid="confirm-dialog"
            onCancel={(e) => { e.preventDefault(); onCancel(); }}>
      <h2 id="dialog-title">{title}</h2>
      <p>{message}</p>
      <div className="dialog-actions">
        <button type="button" className="ghost" onClick={onCancel} data-testid="confirm-cancel">Cancel</button>
        <button type="button" className="danger" onClick={onConfirm} data-testid="confirm-ok" autoFocus>
          {confirmLabel}
        </button>
      </div>
    </dialog>
  );
}
