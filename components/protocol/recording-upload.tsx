"use client";

import { AlertCircle, ArrowRight, CheckCircle2, FileAudio, LoaderCircle, UploadCloud, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { ProcessingResult } from "@/components/protocol/processing-result";

type JobStatus = "idle" | "queued" | "processing" | "completed" | "failed" | "deleting";
type JobStage = "queued" | "preparing" | "diarizing" | "transcribing" | "completed" | "failed";

type JobEvent = {
  stage: JobStage;
  progress_percent: number;
  message: string;
};

type JobResponse = {
  id?: string;
  status?: JobStatus;
  error?: string | null;
  stage?: JobStage;
  progress_percent?: number;
  events?: JobEvent[];
};

const ACCEPTED_EXTENSIONS = [".mp3", ".wav", ".m4a", ".mp4"];
const MAX_UPLOAD_BYTES = 1_073_741_824;
const LAST_JOB_STORAGE_KEY = "hackalem:last-local-job-id";

function isAccepted(file: File) {
  return ACCEPTED_EXTENSIONS.some((extension) => file.name.toLowerCase().endsWith(extension));
}

function formatBytes(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function statusCopy(status: JobStatus, stage?: JobStage) {
  if (stage) return stageCopy(stage);
  switch (status) {
    case "queued":
      return "Запись в очереди";
    case "processing":
      return "Локальная обработка записи";
    case "completed":
      return "Расшифровка готова";
    case "failed":
      return "Обработка не завершилась";
    case "deleting":
      return "Удаляем временные данные";
    default:
      return "Готово к обработке";
  }
}

function stageCopy(stage: JobStage) {
  switch (stage) {
    case "queued":
      return "Запись в очереди";
    case "preparing":
      return "Подготавливаем аудио";
    case "diarizing":
      return "Определяем спикеров";
    case "transcribing":
      return "Распознаём речь";
    case "completed":
      return "Расшифровка готова";
    case "failed":
      return "Обработка не завершилась";
  }
}

function isJobStage(value: unknown): value is JobStage {
  return value === "queued" || value === "preparing" || value === "diarizing" || value === "transcribing" || value === "completed" || value === "failed";
}

function isJobEvent(value: unknown): value is JobEvent {
  return typeof value === "object"
    && value !== null
    && "stage" in value
    && isJobStage(value.stage)
    && "progress_percent" in value
    && typeof value.progress_percent === "number"
    && "message" in value
    && typeof value.message === "string";
}

function isJobId(value: string | null): value is string {
  return value !== null && /^[a-f0-9]{32}$/i.test(value);
}

export function RecordingUpload() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File>();
  const [durationSeconds, setDurationSeconds] = useState<number>();
  const [hasConsent, setHasConsent] = useState(false);
  const [status, setStatus] = useState<JobStatus>("idle");
  const [jobId, setJobId] = useState<string>();
  const [error, setError] = useState<string>();
  const [stage, setStage] = useState<JobStage>();
  const [progressPercent, setProgressPercent] = useState(0);
  const [events, setEvents] = useState<JobEvent[]>([]);
  const [isDragging, setIsDragging] = useState(false);

  const updateJobState = useCallback((next: JobResponse) => {
    if (next.status === "queued" || next.status === "processing" || next.status === "completed" || next.status === "failed" || next.status === "deleting") {
      setStatus(next.status);
    }
    if (isJobStage(next.stage)) setStage(next.stage);
    if (typeof next.progress_percent === "number" && Number.isFinite(next.progress_percent)) {
      setProgressPercent(Math.min(100, Math.max(0, Math.round(next.progress_percent))));
    }
    if (Array.isArray(next.events)) setEvents(next.events.filter(isJobEvent));
    if (next.error) setError(next.error);
  }, []);

  useEffect(() => {
    if (!jobId) return;
    window.localStorage.setItem(LAST_JOB_STORAGE_KEY, jobId);
  }, [jobId]);

  useEffect(() => {
    const savedJobId = window.localStorage.getItem(LAST_JOB_STORAGE_KEY);
    if (!isJobId(savedJobId)) return;
    let current = true;
    const restore = async () => {
      try {
        const response = await fetch(`/api/asr/jobs/${savedJobId}`, { cache: "no-store" });
        const payload: unknown = await response.json().catch(() => ({}));
        if (!current) return;
        if (response.status === 404) {
          window.localStorage.removeItem(LAST_JOB_STORAGE_KEY);
          return;
        }
        if (!response.ok || typeof payload !== "object" || payload === null) return;
        setJobId(savedJobId);
        updateJobState(payload as JobResponse);
      } catch {
        // The saved result remains available when the local service is started again.
      }
    };
    void restore();
    return () => {
      current = false;
    };
  }, [updateJobState]);

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
        updateJobState(next);
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
  }, [jobId, status, updateJobState]);

  const selectFile = (nextFile: File | undefined) => {
    if (inputRef.current) inputRef.current.value = "";
    setError(undefined);
    setJobId(undefined);
    setStatus("idle");
    setStage(undefined);
    setProgressPercent(0);
    setEvents([]);
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
    let submitted = false;
    try {
      const healthResponse = await fetch("/api/asr/health", { cache: "no-store" });
      const healthPayload: unknown = await healthResponse.json().catch(() => ({}));
      if (!healthResponse.ok) throw new Error("Локальный ASR-сервис недоступен. Проверьте его состояние справа.");
      if (typeof healthPayload === "object" && healthPayload !== null && "ready" in healthPayload
        && typeof healthPayload.ready === "object" && healthPayload.ready !== null
        && "transcription" in healthPayload.ready && healthPayload.ready.transcription === false) {
        throw new Error("Для расшифровки не хватает обязательных компонентов. Откройте подсказки в блоке «Состояние сервиса».");
      }
      setStatus("queued");
      submitted = true;
      const formData = new FormData();
      formData.set("file", file);
      const response = await fetch("/api/asr/transcribe", { method: "POST", body: formData });
      const payload: unknown = await response.json().catch(() => ({}));
      const result = typeof payload === "object" && payload !== null ? (payload as JobResponse) : {};
      if (!response.ok || !result.id || !result.status) {
        throw new Error(result.error ?? "Локальный сервис не принял запись.");
      }
      setJobId(result.id);
      updateJobState(result);
    } catch (caughtError) {
      setStatus(submitted ? "failed" : "idle");
      setError(caughtError instanceof Error ? caughtError.message : "Не удалось запустить обработку.");
    }
  };

  const active = status === "queued" || status === "processing";

  return (
    <section className="rounded-[28px] border surface p-5 shadow-[0_20px_70px_-50px_rgba(19,61,45,0.28)] sm:p-8" aria-live="polite" aria-labelledby="upload-title">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-accent">Шаг 01 / 03</p>
          <h2 id="upload-title" className="mt-2 text-2xl font-semibold tracking-[-0.04em] sm:text-[28px]">Добавьте запись встречи</h2>
          <p className="mt-2 max-w-xl text-sm leading-6 text-muted">Выберите аудио или видео. Файл передаётся только локальному сервису на этом компьютере.</p>
        </div>
      </div>

      <label
        className={`mt-7 flex min-h-60 cursor-pointer flex-col items-center justify-center rounded-[20px] border-2 border-dashed px-5 text-center transition-colors focus-within:border-[rgb(var(--accent))] focus-within:ring-2 focus-within:ring-accent ${isDragging ? "border-[rgb(var(--accent))] bg-accent-soft" : "border-[rgb(var(--border))] bg-[rgb(var(--surface-raised))] hover:border-[rgb(var(--accent))] hover:bg-accent-soft"} ${active ? "pointer-events-none opacity-60" : ""}`}
        onDragEnter={(event) => { event.preventDefault(); setIsDragging(true); }}
        onDragLeave={(event) => { event.preventDefault(); setIsDragging(false); }}
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => {
          event.preventDefault();
          setIsDragging(false);
          if (!active) selectFile(event.dataTransfer.files.item(0) ?? undefined);
        }}
      >
        <input
          ref={inputRef}
          className="sr-only"
          type="file"
          accept="audio/mpeg,audio/wav,audio/mp4,video/mp4,.mp3,.wav,.m4a,.mp4"
          onChange={(event) => selectFile(event.target.files?.item(0) ?? undefined)}
          disabled={active}
        />
        <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-white text-accent shadow-sm dark:bg-[rgb(var(--surface))]">
          <UploadCloud className="h-6 w-6" strokeWidth={1.8} aria-hidden="true" />
        </span>
        <span className="mt-5 text-base font-semibold">Перетащите файл сюда</span>
        <span className="mt-1 text-sm text-muted">или <span className="font-semibold text-accent underline underline-offset-4">выберите на компьютере</span></span>
        <span className="mt-5 text-xs text-muted">MP3, WAV, M4A, MP4 · до 1 ГиБ</span>
      </label>

      {file ? (
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-2xl border bg-[rgb(var(--surface-raised))] p-4">
          <div className="flex min-w-0 items-center gap-3">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-accent-soft"><FileAudio className="h-5 w-5 text-accent" aria-hidden="true" /></span>
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
            <X className="h-4 w-4" aria-hidden="true" /> Убрать
          </Button>
        </div>
      ) : null}

      <label className="mt-5 flex cursor-pointer items-start gap-3 text-sm leading-6">
        <input
          className="mt-0.5 h-4 w-4 rounded border-[rgb(var(--border))] text-[rgb(var(--accent))]"
          type="checkbox"
          checked={hasConsent}
          onChange={(event) => setHasConsent(event.target.checked)}
          disabled={active}
        />
        <span className="text-muted">Подтверждаю, что участники уведомлены о записи и обработке.</span>
      </label>

      <div className="mt-7 flex flex-wrap items-center justify-between gap-4 border-t pt-6">
        <div className="flex items-center gap-2 text-xs text-muted">
          {active ? <LoaderCircle className="h-4 w-4 animate-spin text-accent" aria-hidden="true" /> : status === "completed" ? <CheckCircle2 className="h-4 w-4 text-emerald-600" aria-hidden="true" /> : null}
          <span>{statusCopy(status, stage)}</span>
        </div>
        <Button className="w-full sm:w-auto sm:min-w-52" onClick={() => void upload()} disabled={!file || !hasConsent || active}>
          {active ? "Обрабатываем…" : "Начать обработку"}
          {!active ? <ArrowRight className="h-4 w-4" aria-hidden="true" /> : null}
        </Button>
      </div>

      {jobId ? (
        <div className="mt-5 rounded-xl border bg-[rgb(var(--surface-raised))] p-4">
          <div className="flex items-center justify-between gap-3 text-sm">
            <p className="font-medium">Ход локальной обработки</p>
            <span className="font-medium text-accent">{progressPercent}%</span>
          </div>
          <div
            className="mt-3 h-2 overflow-hidden rounded-full bg-[rgb(var(--border))]"
            role="progressbar"
            aria-label="Прогресс локальной обработки"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={progressPercent}
          >
            <div className="h-full rounded-full bg-accent transition-all duration-500" style={{ width: `${progressPercent}%` }} />
          </div>
          <details className="mt-4 border-t pt-3">
            <summary className="cursor-pointer text-xs font-medium text-muted">Подробности обработки</summary>
            <ol className="mt-3 space-y-2 text-sm">
              {events.map((event, index) => (
                <li key={`${event.stage}-${event.progress_percent}-${index}`} className="flex gap-3 text-muted">
                  <span className="w-9 shrink-0 text-right font-medium text-accent">{event.progress_percent}%</span>
                  <span>{event.message}</span>
                </li>
              ))}
            </ol>
          </details>
        </div>
      ) : null}

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
