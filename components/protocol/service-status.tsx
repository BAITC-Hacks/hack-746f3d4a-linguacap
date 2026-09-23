"use client";

import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";

type ServiceHealth = {
  status?: string;
  error?: string;
  device?: { requested?: string; selected?: string; fallback_reason?: string | null };
  ffmpeg?: string;
  models?: Record<string, { state?: string }>;
};

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

    return () => {
      isCurrent = false;
    };
  }, [requestHealth]);

  const checkHealth = async () => {
    setIsChecking(true);
    setHealth(await requestHealth());
    setIsChecking(false);
  };

  const isReady = health?.status === "ok";
  const modelCount = Object.values(health?.models ?? {}).filter((model) => model.state === "available").length;

  return (
    <section className="rounded-2xl border surface p-5 shadow-sm sm:p-6" aria-live="polite">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-accent">Локальная инфраструктура</p>
          <h2 className="mt-1 text-xl font-semibold">ASR-сервис</h2>
          <p className="mt-2 max-w-xl text-sm leading-6 text-muted">
            {isChecking
              ? "Проверяем сервис на этом компьютере…"
              : isReady
                ? "Сервис доступен. Обработка аудио останется внутри локального контура."
                : health?.error ?? "Сервис пока не запущен."}
          </p>
        </div>
        <Button onClick={() => void checkHealth()} disabled={isChecking} variant="secondary">
          {isChecking ? "Проверяем…" : "Проверить снова"}
        </Button>
      </div>

      {isReady ? (
        <dl className="mt-5 grid gap-3 border-t pt-5 text-sm sm:grid-cols-3">
          <div>
            <dt className="text-muted">Устройство</dt>
            <dd className="mt-1 font-medium">{health.device?.selected ?? "—"} <span className="font-normal text-muted">(запрошено: {health.device?.requested ?? "—"})</span></dd>
          </div>
          <div>
            <dt className="text-muted">FFmpeg</dt>
            <dd className="mt-1 font-medium">{health.ffmpeg === "available" ? "доступен" : "не найден"}</dd>
          </div>
          <div>
            <dt className="text-muted">Локальные модели</dt>
            <dd className="mt-1 font-medium">{modelCount} из {Object.keys(health.models ?? {}).length} подготовлено</dd>
          </div>
        </dl>
      ) : null}
    </section>
  );
}
