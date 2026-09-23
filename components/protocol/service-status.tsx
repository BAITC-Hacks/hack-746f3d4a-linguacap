"use client";

import { AlertCircle, Check, RotateCw, Server } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";

type ComponentState = "available" | "not_found" | "not_downloaded" | "disabled" | "unavailable";
type ServiceHealth = {
  status?: string;
  error?: string;
  device?: { selected?: string; fallback_reason?: string | null };
  ffmpeg?: ComponentState;
  ffprobe?: ComponentState;
  dependencies?: Record<string, ComponentState>;
  models?: Record<string, { state?: ComponentState }>;
  ready?: Record<string, boolean>;
  startup_error?: string | null;
  analysis_model?: string | null;
};

type CheckItem = {
  label: string;
  ready: boolean;
  optional?: boolean;
  detail: string;
  command?: string;
};

function setupChecks(health: ServiceHealth): CheckItem[] {
  const pyannoteReady = health.dependencies?.pyannote === "available";
  const diarizationReady = health.models?.diarization?.state === "available";
  const nemoReady = health.dependencies?.nemo === "available";
  const nemoModelReady = health.models?.asr_nemo?.state === "available";
  const llmState = health.models?.llm?.state;
  return [
    {
      label: "FFmpeg и FFprobe",
      ready: health.ffmpeg === "available" && health.ffprobe === "available",
      detail: "Нужны для подготовки записи.",
      command: "brew install ffmpeg",
    },
    {
      label: "PyTorch",
      ready: health.dependencies?.torch === "available",
      detail: "Нужен для локального распознавания.",
      command: "cd services/asr && make install",
    },
    {
      label: "Модель распознавания Rukk",
      ready: health.models?.asr_rukk?.state === "available" && !health.startup_error,
      detail: health.startup_error ?? "Нужна для расшифровки русской и казахской речи.",
      command: "cd services/asr && make download-rukk",
    },
    {
      label: "Спикеры · pyannote",
      ready: pyannoteReady && diarizationReady,
      optional: true,
      detail: !pyannoteReady ? "Не установлен Python-пакет для определения спикеров." : "Не найдена модель. Для её загрузки нужен доступ к gated-модели на Hugging Face.",
      command: !pyannoteReady ? "cd services/asr && make install-diarization" : "cd services/asr && make download-pyannote",
    },
    {
      label: "NeMo · модель для сравнения",
      ready: nemoReady && nemoModelReady,
      optional: true,
      detail: !nemoReady ? "Среда NeMo не установлена. Для обычной расшифровки она не нужна." : "Архив модели NeMo не найден. Для обычной расшифровки он не нужен.",
      command: !nemoReady ? "cd services/asr && make install-nemo" : "cd services/asr && make download-nemo",
    },
    {
      label: "Саммари и поручения · Ollama",
      ready: llmState === "available",
      optional: true,
      detail: llmState === "disabled" ? "Локальный анализ выключен. Добавьте эти строки в services/asr/.env и перезапустите сервис."
        : llmState === "unavailable" ? "Локальный сервис Ollama не отвечает."
          : "Выбранная модель отсутствует в Ollama.",
      command: llmState === "disabled" ? "ASR_LOCAL_LLM_PROVIDER=ollama\nASR_LOCAL_LLM_MODEL=qwen3:4b"
        : llmState === "unavailable" ? "OLLAMA_HOST=127.0.0.1:11434 ollama serve"
          : `ollama pull ${health.analysis_model ?? "qwen3:4b"}`,
    },
    {
      label: "Экспорт DOCX",
      ready: health.dependencies?.docx === "available",
      optional: true,
      detail: "В окружении ASR-сервиса не установлен python-docx.",
      command: "python3 -m pip install python-docx==1.1.2",
    },
    {
      label: "Экспорт PDF",
      ready: health.dependencies?.reportlab === "available",
      optional: true,
      detail: "В окружении ASR-сервиса не установлен reportlab.",
      command: "python3 -m pip install reportlab==4.2.5",
    },
  ];
}

export function ServiceStatus() {
  const [health, setHealth] = useState<ServiceHealth>();
  const [isChecking, setIsChecking] = useState(true);

  const requestHealth = useCallback(async (): Promise<ServiceHealth> => {
    try {
      const response = await fetch("/api/asr/health", { cache: "no-store" });
      const payload: unknown = await response.json().catch(() => ({}));
      return typeof payload === "object" && payload !== null ? (payload as ServiceHealth) : { error: "Сервис вернул некорректный ответ." };
    } catch {
      return { error: "Не удалось проверить локальный ASR-сервис." };
    }
  }, []);

  useEffect(() => {
    let isCurrent = true;
    void requestHealth().then((nextHealth) => {
      if (!isCurrent) return;
      setHealth(nextHealth);
      setIsChecking(false);
    });
    return () => { isCurrent = false; };
  }, [requestHealth]);

  const checkHealth = async () => {
    setIsChecking(true);
    setHealth(await requestHealth());
    setIsChecking(false);
  };

  const serviceOnline = health?.status === "ok";
  const canTranscribe = health?.ready?.transcription === true;
  const checks = serviceOnline && health?.ready ? setupChecks(health) : [];
  const missing = checks.filter((item) => !item.ready);
  const summary = isChecking ? "Проверяем компоненты"
    : !serviceOnline ? "Сервис недоступен"
      : !health?.ready ? "Нужен перезапуск сервиса"
      : canTranscribe ? missing.length ? "Расшифровка готова" : "Всё готово"
        : "Нужна настройка";

  return (
    <section className="rounded-[24px] border surface p-6 sm:p-7" aria-live="polite" aria-labelledby="service-title">
      <div className="flex items-center justify-between gap-3">
        <h2 id="service-title" className="text-base font-semibold tracking-[-0.025em]">Состояние сервиса</h2>
        <Server className="h-4 w-4 text-muted" aria-hidden="true" />
      </div>
      <div className="mt-6 flex items-start gap-3">
        <span className={`mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full ${isChecking ? "bg-amber-400" : canTranscribe ? "bg-emerald-500" : "bg-amber-500"}`} aria-hidden="true" />
        <div className="min-w-0">
          <p className="text-sm font-semibold">{summary}</p>
          <p className="mt-1 text-xs leading-5 text-muted">
            {isChecking ? "Проверяем локальный сервис…"
              : !serviceOnline ? health?.error ?? "Запустите локальный ASR-сервис."
                : !health?.ready ? "Обновите локальный ASR-сервис, чтобы увидеть диагностику компонентов."
                  : canTranscribe ? missing.length ? `${missing.length} дополнительных компонентов требуют настройки.` : `Все этапы доступны · ${health.device?.selected ?? "CPU"}`
                    : "Для расшифровки не хватает обязательных компонентов."}
          </p>
        </div>
      </div>

      {serviceOnline && checks.length ? (
        <div className="mt-5 border-t pt-4">
          <div className="space-y-3">
            {checks.map((item) => (
              <div key={item.label} className="flex items-start gap-2.5 text-xs">
                {item.ready ? <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-600" aria-hidden="true" />
                  : <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-600" aria-hidden="true" />}
                <span className={item.ready ? "text-muted" : "font-medium"}>{item.label}{item.optional ? " · доп." : ""}</span>
              </div>
            ))}
          </div>
          {health?.startup_error ? <p className="mt-4 text-xs leading-5 text-amber-800 dark:text-amber-200">{health.startup_error}</p> : null}
          {missing.length ? (
            <details className="mt-5 rounded-xl bg-[rgb(var(--surface-raised))] p-3 text-xs">
              <summary className="cursor-pointer font-medium text-accent">Что нужно установить или запустить</summary>
              <ul className="mt-3 space-y-4">
                {missing.map((item) => (
                  <li key={item.label}>
                    <p className="font-semibold">{item.label}</p>
                    <p className="mt-1 leading-5 text-muted">{item.detail}</p>
                    {item.command ? <code className="mt-2 block whitespace-pre-wrap break-all rounded-lg border bg-[rgb(var(--surface))] p-2 text-[11px] leading-5">{item.command}</code> : null}
                  </li>
                ))}
              </ul>
              <p className="mt-4 leading-5 text-muted">Системные компоненты и модели устанавливаются в терминале. После установки перезапустите ASR-сервис и проверьте состояние снова. Загрузка моделей требует интернета только при установке.</p>
            </details>
          ) : null}
        </div>
      ) : null}

      {!isChecking && !serviceOnline ? (
        <p className="mt-4 rounded-xl bg-[rgb(var(--surface-raised))] p-3 text-xs leading-5 text-muted">
          Если окружение уже установлено, запустите <code>npm run dev:asr:full</code> в отдельном терминале.
        </p>
      ) : null}

      <Button className="mt-5 w-full" onClick={() => void checkHealth()} disabled={isChecking} variant="secondary" size="sm">
        <RotateCw className={`h-3.5 w-3.5 ${isChecking ? "animate-spin" : ""}`} aria-hidden="true" />
        {isChecking ? "Проверяем…" : "Проверить снова"}
      </Button>
    </section>
  );
}
