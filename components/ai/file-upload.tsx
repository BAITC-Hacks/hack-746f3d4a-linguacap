"use client";

import { FileUp, Paperclip, X } from "lucide-react";
import { useId, useRef, useState } from "react";

import { Button } from "@/components/ui/button";

type FileUploadProps = {
  disabled?: boolean;
  onFilesChange?: (files: File[]) => void;
};

export function FileUpload({ disabled, onFilesChange }: FileUploadProps) {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [isDragging, setIsDragging] = useState(false);

  const updateFiles = (nextFiles: File[]) => {
    const uniqueFiles = Array.from(new Map(nextFiles.map((file) => [`${file.name}-${file.size}-${file.lastModified}`, file])).values()).slice(0, 5);
    setFiles(uniqueFiles);
    onFilesChange?.(uniqueFiles);
  };

  const addFiles = (fileList: FileList | null) => {
    if (!fileList) return;
    updateFiles([...files, ...Array.from(fileList)]);
  };

  return (
    <div className="space-y-2">
      <input
        className="sr-only"
        disabled={disabled}
        id={inputId}
        multiple
        onChange={(event) => {
          addFiles(event.target.files);
          event.target.value = "";
        }}
        ref={inputRef}
        type="file"
      />
      <div
        className={`flex items-center justify-between gap-3 rounded-xl border border-dashed px-3 py-2 transition ${
          isDragging ? "border-[rgb(var(--accent))] bg-[rgb(var(--accent-soft))]" : "surface-raised"
        }`}
        onDragEnter={(event) => {
          event.preventDefault();
          if (!disabled) setIsDragging(true);
        }}
        onDragLeave={(event) => {
          event.preventDefault();
          setIsDragging(false);
        }}
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => {
          event.preventDefault();
          setIsDragging(false);
          if (!disabled) addFiles(event.dataTransfer.files);
        }}
      >
        <div className="flex min-w-0 items-center gap-2">
          <FileUp aria-hidden="true" className="h-4 w-4 shrink-0 text-accent" />
          <p className="truncate text-xs text-muted">Drop files here or attach context for a future multimodal request.</p>
        </div>
        <Button aria-label="Choose files" disabled={disabled} onClick={() => inputRef.current?.click()} size="sm" variant="ghost">
          <Paperclip aria-hidden="true" className="h-4 w-4" />
          Attach
        </Button>
      </div>
      {files.length > 0 && (
        <div aria-live="polite" className="flex flex-wrap gap-2">
          {files.map((file) => (
            <span className="inline-flex max-w-full items-center gap-1.5 rounded-lg bg-[rgb(var(--accent-soft))] px-2.5 py-1 text-xs text-[rgb(var(--foreground))]" key={`${file.name}-${file.size}-${file.lastModified}`}>
              <span className="truncate">{file.name}</span>
              <button
                aria-label={`Remove ${file.name}`}
                className="rounded p-0.5 hover:bg-black/10 dark:hover:bg-white/10"
                disabled={disabled}
                onClick={() => updateFiles(files.filter((candidate) => candidate !== file))}
                type="button"
              >
                <X aria-hidden="true" className="h-3 w-3" />
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
