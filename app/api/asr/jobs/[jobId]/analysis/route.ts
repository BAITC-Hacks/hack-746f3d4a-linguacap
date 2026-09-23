import { z } from "zod";

import { getLocalAsrUrl } from "@/lib/local-asr";
import { jsonWithRequestLog, startRequestLog } from "@/lib/request-log";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const JobIdSchema = z.string().regex(/^[a-f0-9]{32}$/i);

export async function POST(_request: Request, context: { params: Promise<{ jobId: string }> }) {
  const requestLog = startRequestLog("/api/asr/jobs/[jobId]/analysis");
  const { jobId } = await context.params;
  if (!JobIdSchema.safeParse(jobId).success) {
    return jsonWithRequestLog(requestLog, { error: "Некорректный идентификатор задания." }, { status: 400, outcome: "validation_error" });
  }

  try {
    const response = await fetch(getLocalAsrUrl(`/jobs/${jobId}/analysis`), {
      method: "POST",
      cache: "no-store",
      signal: AbortSignal.timeout(185_000),
    });
    const payload: unknown = await response.json().catch(() => null);
    if (!response.ok) {
      const error = response.status === 404
        ? "Задание не найдено."
        : response.status === 409
          ? "Расшифровка ещё не готова."
          : response.status === 422
            ? "Локальная модель не смогла сформировать проверяемый протокол. Попробуйте ещё раз."
            : response.status === 503
              ? "Локальная LLM недоступна. Запустите Ollama и проверьте конфигурацию."
              : "Локальный анализатор ответил с ошибкой.";
      return jsonWithRequestLog(
        requestLog,
        { error },
        { status: response.status === 404 || response.status === 409 || response.status === 422 ? response.status : 503, outcome: "upstream_error" },
      );
    }
    return jsonWithRequestLog(requestLog, payload, { outcome: "success" });
  } catch {
    return jsonWithRequestLog(
      requestLog,
      { error: "Локальный ASR-сервис или Ollama не запущены." },
      { status: 503, outcome: "upstream_unavailable" },
    );
  }
}
