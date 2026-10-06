"use client";

import { useEffect, useRef } from "react";
import { X } from "lucide-react";

/** Accessible modal built on the native <dialog> element (focus trap and Escape for free). */
export function Modal({
  open,
  onClose,
  title,
  description,
  maxWidth = "max-w-lg",
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  maxWidth?: string;
  children: React.ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    if (!open && el.open) el.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      onClick={(e) => e.target === ref.current && onClose()}
      className={`m-auto w-[calc(100%-1.5rem)] ${maxWidth} rounded-2xl border border-border bg-background p-0 text-text shadow-2xl backdrop:bg-black/50 backdrop:backdrop-blur-xs`}
    >
      <div className="p-4 sm:p-6">
        <div className="flex items-start justify-between gap-3 sm:gap-4">
          <div>
            <h2 className="font-heading text-sm sm:text-base font-semibold">{title}</h2>
            {description && <p className="font-sub mt-1 text-xs sm:text-[14px] text-muted">{description}</p>}
          </div>
          <button onClick={onClose} className="rounded-lg p-1 text-muted hover:bg-surface hover:text-text active:scale-95 transition" aria-label="Close">
            <X className="size-4" />
          </button>
        </div>
        <div className="mt-4 sm:mt-5">{children}</div>
      </div>
    </dialog>
  );
}

export function Button({
  variant = "primary",
  className = "",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost" | "danger" }) {
  const styles = {
    primary: "bg-accent text-accent-fg hover:bg-accent-hover",
    ghost: "border border-border hover:bg-surface",
    danger: "bg-error text-white hover:opacity-90",
  }[variant];
  return (
    <button
      className={`rounded-xl px-4 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-60 ${styles} ${className}`}
      {...props}
    />
  );
}

export function ConfirmDialog({
  open,
  onClose,
  onConfirm,
  title,
  description,
  confirmLabel,
}: {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  description: string;
  confirmLabel: string;
}) {
  return (
    <Modal open={open} onClose={onClose} title={title} description={description}>
      <div className="flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>
          Cancel
        </Button>
        <Button
          variant="danger"
          onClick={() => {
            onConfirm();
            onClose();
          }}
        >
          {confirmLabel}
        </Button>
      </div>
    </Modal>
  );
}
