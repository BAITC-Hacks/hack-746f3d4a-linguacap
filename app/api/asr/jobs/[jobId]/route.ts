import { z } from "zod";

import { getLocalAsrUrl } from "@/lib/local-asr";
import { jsonWithRequestLog, startRequestLog } from "@/lib/request-log";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const JobIdSchema = z.string().regex(/^[a-f0-9]{32}$/i);

export async function GET(_request: Request, context: { params: Promise<{ jobId: string }> }) {
  const requestLog = startRequestLog("/api/asr/jobs/[jobId]");
  const { jobId } = await context.params;
  if (!JobIdSchema.safeParse(jobId).success) {
    return jsonWithRequestLog(requestLog, { error: "Некорректный идентификатор задания." }, { status: 400, outcome: "validation_error" });
  }

  try {
    const response = await fetch(getLocalAsrUrl(`/jobs/${jobId}`), {
      cache: "no-store",
      signal: AbortSignal.timeout(3_000),
    });
    const payload: unknown = await response.json().catch(() => null);
    if (!response.ok) {
      return jsonWithRequestLog(
        requestLog,
        { error: response.status === 404 ? "Задание не найдено." : "Локальный ASR-сервис ответил с ошибкой." },
        { status: response.status === 404 ? 404 : 503, outcome: "upstream_error" },
      );
    }
    return jsonWithRequestLog(requestLog, payload, { outcome: "success" });
  } catch {
    return jsonWithRequestLog(
      requestLog,
      { error: "Локальный ASR-сервис не запущен." },
      { status: 503, outcome: "upstream_unavailable" },
    );
  }
}
