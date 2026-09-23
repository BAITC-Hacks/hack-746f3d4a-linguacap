"use client";

import { ArrowUp, Sparkles } from "lucide-react";
import { type FormEvent, useRef } from "react";

import { FileUpload } from "@/components/ai/file-upload";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

type PromptInputProps = {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  disabled?: boolean;
  placeholder?: string;
};

export function PromptInput({ value, onChange, onSubmit, disabled, placeholder = "Ask for ideas, feedback, a summary, or a plan…" }: PromptInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onSubmit();
  };

  return (
    <form className="space-y-3" onSubmit={submit}>
      <label className="sr-only" htmlFor="prompt-input">
        Your prompt
      </label>
      <Textarea
        disabled={disabled}
        id="prompt-input"
        maxLength={6_000}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
            event.preventDefault();
            onSubmit();
          }
        }}
        placeholder={placeholder}
        ref={textareaRef}
        value={value}
      />
      <FileUpload disabled={disabled} />
      <div className="flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs leading-5 text-muted">Text is sent securely from the server. Attachments are kept local for now.</p>
        <Button className="w-full sm:w-auto" disabled={disabled || !value.trim()} type="submit">
          {disabled ? <Sparkles aria-hidden="true" className="h-4 w-4 animate-soft-pulse" /> : <ArrowUp aria-hidden="true" className="h-4 w-4" />}
          {disabled ? "Working…" : "Send prompt"}
        </Button>
      </div>
    </form>
  );
}
