"use client";

import { useState } from "react";
import { Button, Modal } from "@/components/ui/Modal";

export function FeedbackDialog({
  open,
  rating,
  onClose,
  onSubmit,
}: {
  open: boolean;
  rating: 1 | -1;
  onClose: () => void;
  onSubmit: (comment: string) => Promise<void>;
}) {
  const [comment, setComment] = useState("");
  const [saving, setSaving] = useState(false);

  async function submit() {
    setSaving(true);
    await onSubmit(comment.trim());
    setSaving(false);
    setComment("");
    onClose();
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={rating === 1 ? "What was helpful?" : "What went wrong?"}
      description="Optional. Your note helps improve answers for everyone."
    >
      <textarea
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        maxLength={1000}
        rows={4}
        placeholder={rating === 1 ? "Clear and accurate..." : "Outdated, incomplete, or not what I asked..."}
        className="font-sub w-full resize-none rounded-xl border border-border bg-background p-3 text-[15px] outline-none focus:border-accent focus:ring-2 focus:ring-accent/20"
      />
      <div className="mt-4 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>
          Skip
        </Button>
        <Button onClick={submit} disabled={saving}>
          {saving ? "Sending..." : "Send feedback"}
        </Button>
      </div>
    </Modal>
  );
}
