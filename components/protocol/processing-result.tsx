"use client";

import { AlertCircle, ClipboardList, FileText, LoaderCircle, MessageSquareText, PencilLine } from "lucide-react";
import { type FormEvent, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";

type TranscriptSegment = {
  id: string;
  start_seconds: number;
  end_seconds: number;
  text: string;
  speaker_id: string | null;
  speaker_name: string | null;
};

type TranscriptionResult = {
  text: string;
  segments: TranscriptSegment[];
  speakers: Array<{ id: string; display_name: string }>;
};

type MeetingProtocol = {
  title: string;
  summary: string;
  key_points: string[];
  action_items: Array<{
    description: string;
    assignee: string | null;
    deadline_text: string | null;
    deadline: string | null;
    source_segment_ids: string[];
    confidence: number;
    status: "new";
  }>;
};

type Tab = "summary" | "actions" | "transcript";
type AnalysisState = "idle" | "loading" | "ready" | "error";

function timestamp(seconds: number) {
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.floor(seconds % 60);
  return `${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
}

function AnalysisPanel({
  type,
  protocol,
  state,
  error,
  onCreate,
  onOpenSource,
}: {
  type: "summary" | "actions";
  protocol?: MeetingProtocol;
  state: AnalysisState;
  error?: string;
  onCreate: () => void;
  onOpenSource: (segmentId: string) => void;
}) {
  if (state === "loading") {
    return (
      <div className="flex items-center gap-2 rounded-xl border bg-[rgb(var(--surface-raised))] p-5 text-sm text-muted">
        <LoaderCircle className="h-4 w-4 animate-spin text-accent" aria-hidden="true" />
        Локальная модель формирует проверяемый протокол…
      </div>
    );
  }

  if (!protocol) {
    const title = type === "summary" ? "Сформируйте саммари" : "Сформируйте поручения";
    const buttonText = type === "summary" ? "Сформировать саммари" : "Извлечь поручения";
    return (
      <div className="rounded-xl border bg-[rgb(var(--surface-raised))] p-5 text-sm leading-6 text-muted">
        <p className="font-medium text-[rgb(var(--foreground))]">{title}</p>
        <p className="mt-2">Транскрипт будет обработан qwen3:4b только на этом компьютере. Ответственные и сроки без явного подтверждения в реплике останутся пустыми.</p>
        {error ? <p className="mt-3 text-rose-700 dark:text-rose-300">{error}</p> : null}
        <Button className="mt-4" size="sm" onClick={onCreate}>
          <ClipboardList className="h-4 w-4" aria-hidden="true" />
          {buttonText}
        </Button>
      </div>
    );
  }

  if (type === "summary") {
    return (
      <div className="space-y-4">
        <div className="rounded-xl border bg-[rgb(var(--surface-raised))] p-5">
          <p className="text-sm font-medium text-accent">{protocol.title}</p>
          <p className="mt-3 whitespace-pre-wrap text-sm leading-6">{protocol.summary}</p>
        </div>
        {protocol.key_points.length ? (
          <ul className="space-y-2 rounded-xl border bg-[rgb(var(--surface-raised))] p-5 text-sm leading-6">
            {protocol.key_points.map((point, index) => <li key={`${index}-${point}`} className="flex gap-2"><span className="text-accent">•</span><span>{point}</span></li>)}
          </ul>
        ) : null}
      </div>
    );
  }

  if (!protocol.action_items.length) {
    return <p className="rounded-xl border bg-[rgb(var(--surface-raised))] p-5 text-sm text-muted">Явно сформулированных поручений в транскрипте не найдено.</p>;
  }

  return (
    <ol className="space-y-3">
      {protocol.action_items.map((item, index) => (
        <li key={`${index}-${item.description}`} className="rounded-xl border bg-[rgb(var(--surface-raised))] p-4">
          <p className="text-sm leading-6">{item.description}</p>
          <dl className="mt-3 grid gap-x-5 gap-y-1 text-xs text-muted sm:grid-cols-2">
            <div><dt className="inline">Ответственный: </dt><dd className="inline">{item.assignee ?? "не указан"}</dd></div>
            <div><dt className="inline">Срок: </dt><dd className="inline">{item.deadline_text ?? item.deadline ?? "не указан"}</dd></div>
          </dl>
          <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted">
            <span>Источник:</span>
            {item.source_segment_ids.map((segmentId) => (
              <Button key={segmentId} size="sm" variant="secondary" onClick={() => onOpenSource(segmentId)}>{segmentId}</Button>
            ))}
          </div>
        </li>
      ))}
    </ol>
  );
}

function SpeakerRenameForm({
  jobId,
  speakerId,
  displayName,
  onRenamed,
}: {
  jobId: string;
  speakerId: string;
  displayName: string;
  onRenamed: (speakerId: string, displayName: string) => void;
}) {
  const [value, setValue] = useState(displayName);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string>();

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const nextName = value.trim();
    if (!nextName) {
      setError("Введите имя спикера.");
      return;
    }
    setIsSaving(true);
    setError(undefined);
    try {
      const response = await fetch(`/api/asr/jobs/${jobId}/speakers/${speakerId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ display_name: nextName }),
      });
      const payload: unknown = await response.json().catch(() => ({}));
      if (!response.ok || typeof payload !== "object" || payload === null || !("display_name" in payload) || typeof payload.display_name !== "string") {
        throw new Error("Не удалось сохранить имя спикера.");
      }
      setValue(payload.display_name);
      onRenamed(speakerId, payload.display_name);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Не удалось сохранить имя спикера.");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <form className="flex flex-wrap items-end gap-2" onSubmit={(event) => void submit(event)}>
      <label className="flex min-w-48 flex-1 flex-col gap-1 text-xs text-muted">
        <span>{speakerId}</span>
        <input
          className="min-h-10 rounded-lg border bg-[rgb(var(--surface))] px-3 text-sm text-[rgb(var(--foreground))] outline-none ring-accent focus:ring-2"
          value={value}
          maxLength={100}
          onChange={(event) => setValue(event.target.value)}
          disabled={isSaving}
        />
      </label>
      <Button size="sm" variant="secondary" type="submit" disabled={isSaving || value.trim() === displayName}>
        <PencilLine className="h-4 w-4" aria-hidden="true" />
        {isSaving ? "Сохраняем…" : "Переименовать"}
      </Button>
      {error ? <p className="basis-full text-xs text-rose-700 dark:text-rose-300">{error}</p> : null}
    </form>
  );
}

export function ProcessingResult({ jobId }: { jobId: string }) {
  const [result, setResult] = useState<TranscriptionResult>();
  const [tab, setTab] = useState<Tab>("transcript");
  const [error, setError] = useState<string>();
  const [speakerNames, setSpeakerNames] = useState<Record<string, string>>({});
  const [protocol, setProtocol] = useState<MeetingProtocol>();
  const [analysisState, setAnalysisState] = useState<AnalysisState>("idle");
  const [analysisError, setAnalysisError] = useState<string>();

  useEffect(() => {
    let current = true;
    const load = async () => {
      try {
        const response = await fetch(`/api/asr/jobs/${jobId}/result`, { cache: "no-store" });
        const payload: unknown = await response.json().catch(() => ({}));
        if (!current) return;
        if (!response.ok || typeof payload !== "object" || payload === null) {
          const message = typeof payload === "object" && payload !== null && "error" in payload && typeof payload.error === "string"
            ? payload.error
            : "Не удалось получить результат локального задания.";
          throw new Error(message);
        }
        setResult(payload as TranscriptionResult);
      } catch (caughtError) {
        if (current) setError(caughtError instanceof Error ? caughtError.message : "Не удалось получить результат локального задания.");
      }
    };
    void load();
    return () => {
      current = false;
    };
  }, [jobId]);

  const createAnalysis = async () => {
    if (analysisState === "loading" || protocol) return;
    setAnalysisState("loading");
    setAnalysisError(undefined);
    try {
      const response = await fetch(`/api/asr/jobs/${jobId}/analysis`, { method: "POST" });
      const payload: unknown = await response.json().catch(() => ({}));
      if (!response.ok || !isMeetingProtocol(payload)) {
        const message = typeof payload === "object" && payload !== null && "error" in payload && typeof payload.error === "string"
          ? payload.error
          : "Не удалось сформировать локальный протокол.";
        throw new Error(message);
      }
      setProtocol(payload);
      setAnalysisState("ready");
    } catch (caughtError) {
      setAnalysisState("error");
      setAnalysisError(caughtError instanceof Error ? caughtError.message : "Не удалось сформировать локальный протокол.");
    }
  };

  const openSource = (segmentId: string) => {
    setTab("transcript");
    window.setTimeout(() => document.getElementById(`segment-${segmentId}`)?.scrollIntoView({ behavior: "smooth", block: "center" }), 0);
  };

  if (error) {
    return (
      <p className="mt-6 flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800 dark:border-rose-950 dark:bg-rose-950/30 dark:text-rose-200">
        <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        {error}
      </p>
    );
  }

  if (!result) {
    return (
      <p className="mt-6 flex items-center gap-2 rounded-xl border bg-[rgb(var(--surface-raised))] p-4 text-sm text-muted">
        <LoaderCircle className="h-4 w-4 animate-spin text-accent" aria-hidden="true" />
        Загружаем локальный результат…
      </p>
    );
  }

  return (
    <section className="mt-6 rounded-2xl border surface p-5 shadow-sm sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-accent">Результат обработки</p>
          <h2 className="mt-1 text-xl font-semibold">Расшифровка готова</h2>
          <p className="mt-2 text-sm text-muted">{result.segments.length} сегм. · результат хранится локально до закрытия задания.</p>
        </div>
      </div>

      <div className="mt-5 flex flex-wrap gap-2 border-b pb-4" role="tablist" aria-label="Разделы результата">
        <Button role="tab" aria-selected={tab === "transcript"} variant={tab === "transcript" ? "primary" : "secondary"} size="sm" onClick={() => setTab("transcript")}>
          <MessageSquareText className="h-4 w-4" aria-hidden="true" /> Транскрипт
        </Button>
        <Button role="tab" aria-selected={tab === "summary"} variant={tab === "summary" ? "primary" : "secondary"} size="sm" onClick={() => setTab("summary")}>
          <FileText className="h-4 w-4" aria-hidden="true" /> Саммари
        </Button>
        <Button role="tab" aria-selected={tab === "actions"} variant={tab === "actions" ? "primary" : "secondary"} size="sm" onClick={() => setTab("actions")}>
          <ClipboardList className="h-4 w-4" aria-hidden="true" /> Поручения
        </Button>
      </div>

      <div className="mt-5" role="tabpanel">
        {tab === "summary" ? <AnalysisPanel type="summary" protocol={protocol} state={analysisState} error={analysisError} onCreate={() => void createAnalysis()} onOpenSource={openSource} /> : null}
        {tab === "actions" ? <AnalysisPanel type="actions" protocol={protocol} state={analysisState} error={analysisError} onCreate={() => void createAnalysis()} onOpenSource={openSource} /> : null}
        {tab === "transcript" ? (
          <>
            {result.speakers.length ? (
              <div className="mb-4 grid gap-3 rounded-xl border bg-[rgb(var(--surface-raised))] p-4 sm:grid-cols-2">
                {result.speakers.map((speaker) => (
                  <SpeakerRenameForm
                    key={speaker.id}
                    jobId={jobId}
                    speakerId={speaker.id}
                    displayName={speakerNames[speaker.id] ?? speaker.display_name}
                    onRenamed={(speakerId, displayName) => setSpeakerNames((current) => ({ ...current, [speakerId]: displayName }))}
                  />
                ))}
              </div>
            ) : null}
            <ol className="space-y-3">
              {result.segments.map((segment) => (
                <li id={`segment-${segment.id}`} key={segment.id} className="rounded-xl border bg-[rgb(var(--surface-raised))] p-4">
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
                    <span className="font-medium text-accent">{segment.speaker_id ? speakerNames[segment.speaker_id] ?? segment.speaker_name ?? segment.speaker_id : "Спикер не определён"}</span>
                    <span>{timestamp(segment.start_seconds)}–{timestamp(segment.end_seconds)}</span>
                  </div>
                  <p className="mt-2 whitespace-pre-wrap text-sm leading-6">{segment.text}</p>
                </li>
              ))}
            </ol>
          </>
        ) : null}
      </div>
    </section>
  );
}

function isMeetingProtocol(value: unknown): value is MeetingProtocol {
  if (typeof value !== "object" || value === null) return false;
  const protocol = value as Partial<MeetingProtocol>;
  return typeof protocol.title === "string"
    && typeof protocol.summary === "string"
    && Array.isArray(protocol.key_points)
    && protocol.key_points.every((item) => typeof item === "string")
    && Array.isArray(protocol.action_items);
}
