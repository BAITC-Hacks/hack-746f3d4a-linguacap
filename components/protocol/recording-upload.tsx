"use client";

import { AlertCircle, CheckCircle2, FileAudio, LoaderCircle, ShieldCheck, Upload } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { ProcessingResult } from "@/components/protocol/processing-result";

type JobStatus = "idle" | "queued" | "processing" | "completed" | "failed";

type JobResponse = {
  id?: string;
  status?: JobStatus;
  error?: string | null;
};

const ACCEPTED_EXTENSIONS = [".mp3", ".wav", ".m4a", ".mp4"];
const MAX_UPLOAD_BYTES = 1_073_741_824;

function isAccepted(file: File) {
  return ACCEPTED_EXTENSIONS.some((extension) => file.name.toLowerCase().endsWith(extension));
}

function formatBytes(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function statusCopy(status: JobStatus) {
  switch (status) {
    case "queued":
      return "Запись в очереди";
    case "processing":
      return "Локальная обработка записи";
    case "completed":
      return "Расшифровка готова";
    case "failed":
      return "Обработка не завершилась";
    default:
      return "Готово к обработке";
  }
}

export function RecordingUpload() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File>();
  const [durationSeconds, setDurationSeconds] = useState<number>();
  const [hasConsent, setHasConsent] = useState(false);
  const [status, setStatus] = useState<JobStatus>("idle");
  const [jobId, setJobId] = useState<string>();
  const [error, setError] = useState<string>();

  useEffect(() => {
    if (!file) return;
    const audio = document.createElement("audio");
    const url = URL.createObjectURL(file);
    audio.preload = "metadata";
    audio.onloadedmetadata = () => {
      setDurationSeconds(Number.isFinite(audio.duration) ? audio.duration : undefined);
      URL.revokeObjectURL(url);
    };
    audio.onerror = () => {
      setDurationSeconds(undefined);
      URL.revokeObjectURL(url);
    };
    audio.src = url;
    return () => URL.revokeObjectURL(url);
  }, [file]);

  useEffect(() => {
    if (!jobId || status === "completed" || status === "failed") return;
    let current = true;
    const poll = async () => {
      try {
        const response = await fetch(`/api/asr/jobs/${jobId}`, { cache: "no-store" });
        const payload: unknown = await response.json().catch(() => ({}));
        if (!current || typeof payload !== "object" || payload === null) return;
        const next = payload as JobResponse;
        if (next.status === "queued" || next.status === "processing" || next.status === "completed" || next.status === "failed") {
          setStatus(next.status);
          if (next.error) setError(next.error);
        }
      } catch {
        if (current) setError("Не удалось получить статус локального задания.");
      }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 1_500);
    return () => {
      current = false;
      window.clearInterval(timer);
    };
  }, [jobId, status]);

  const selectFile = (nextFile: File | undefined) => {
    setError(undefined);
    setJobId(undefined);
    setStatus("idle");
    setDurationSeconds(undefined);
    if (!nextFile) return;
    if (!isAccepted(nextFile)) {
      setFile(undefined);
      setError("Поддерживаются MP3, WAV, M4A и MP4.");
      return;
    }
    if (nextFile.size > MAX_UPLOAD_BYTES) {
      setFile(undefined);
      setError("Размер записи не должен превышать 1 GiB.");
      return;
    }
    setFile(nextFile);
  };

  const upload = async () => {
    if (!file || !hasConsent) return;
    setError(undefined);
    setStatus("queued");
    try {
      const formData = new FormData();
      formData.set("file", file);
      const response = await fetch("/api/asr/transcribe", { method: "POST", body: formData });
      const payload: unknown = await response.json().catch(() => ({}));
      const result = typeof payload === "object" && payload !== null ? (payload as JobResponse) : {};
      if (!response.ok || !result.id || !result.status) {
        throw new Error(result.error ?? "Локальный сервис не принял запись.");
      }
      setJobId(result.id);
      setStatus(result.status);
    } catch (caughtError) {
      setStatus("failed");
      setError(caughtError instanceof Error ? caughtError.message : "Не удалось запустить обработку.");
    }
  };

  const active = status === "queued" || status === "processing";

  return (
    <section className="rounded-2xl border surface p-5 shadow-sm sm:p-6" aria-live="polite">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-accent">Новая запись</p>
          <h2 className="mt-1 text-xl font-semibold">Загрузить совещание</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-muted">
            Файл остаётся на этом компьютере: браузер передаст его только в локальный сервис обработки.
          </p>
        </div>
        <div className="flex items-center gap-2 rounded-full bg-accent-soft px-3 py-1.5 text-xs font-medium text-accent">
          <ShieldCheck className="h-4 w-4" aria-hidden="true" />
          Локальный контур
        </div>
      </div>

      <label
        className="mt-5 flex min-h-44 cursor-pointer flex-col items-center justify-center rounded-2xl border border-dashed bg-[rgb(var(--surface-raised))] px-5 text-center transition hover:bg-accent-soft"
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => {
          event.preventDefault();
          selectFile(event.dataTransfer.files.item(0) ?? undefined);
        }}
      >
        <input
          ref={inputRef}
          className="sr-only"
          type="file"
          accept="audio/mpeg,audio/wav,audio/mp4,video/mp4,.mp3,.wav,.m4a,.mp4"
          onChange={(event) => selectFile(event.target.files?.item(0) ?? undefined)}
        />
        <Upload className="h-7 w-7 text-accent" aria-hidden="true" />
        <span className="mt-3 font-medium">Перетащите запись сюда или выберите файл</span>
        <span className="mt-1 text-sm text-muted">MP3, WAV, M4A или MP4 · до 1 GiB</span>
      </label>

      {file ? (
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border bg-[rgb(var(--surface-raised))] p-4">
          <div className="flex min-w-0 items-center gap-3">
            <FileAudio className="h-5 w-5 shrink-0 text-accent" aria-hidden="true" />
            <div className="min-w-0">
              <p className="truncate text-sm font-medium">{file.name}</p>
              <p className="mt-1 text-xs text-muted">
                {formatBytes(file.size)}{durationSeconds ? ` · ${Math.ceil(durationSeconds)} с` : ""}
              </p>
            </div>
          </div>
          <Button
            variant="ghost"
            size="sm"
            disabled={active}
            onClick={(event) => {
              event.preventDefault();
              event.stopPropagation();
              selectFile(undefined);
            }}
          >
            Убрать
          </Button>
        </div>
      ) : null}

      <label className="mt-4 flex cursor-pointer items-start gap-3 rounded-xl bg-[rgb(var(--surface-raised))] p-4 text-sm leading-5">
        <input
          className="mt-0.5 h-4 w-4 rounded border-[rgb(var(--border))] text-[rgb(var(--accent))]"
          type="checkbox"
          checked={hasConsent}
          onChange={(event) => setHasConsent(event.target.checked)}
          disabled={active}
        />
        <span>Подтверждаю, что участники совещания уведомлены о записи и обработке.</span>
      </label>

      <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm text-muted">
          {active ? <LoaderCircle className="h-4 w-4 animate-spin text-accent" aria-hidden="true" /> : status === "completed" ? <CheckCircle2 className="h-4 w-4 text-emerald-600" aria-hidden="true" /> : null}
          <span>{statusCopy(status)}</span>
        </div>
        <Button onClick={() => void upload()} disabled={!file || !hasConsent || active}>
          {active ? "Обрабатываем…" : "Начать обработку"}
        </Button>
      </div>

      {error ? (
        <p className="mt-4 flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800 dark:border-rose-950 dark:bg-rose-950/30 dark:text-rose-200">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          {error}
        </p>
      ) : null}

      {status === "completed" && jobId ? <ProcessingResult jobId={jobId} /> : null}
    </section>
  );
}
