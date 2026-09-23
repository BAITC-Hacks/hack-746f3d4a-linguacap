import { z } from "zod";

import { getLocalAsrUrl } from "@/lib/local-asr";
import { jsonWithRequestLog, startRequestLog } from "@/lib/request-log";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const JobIdSchema = z.string().regex(/^[a-f0-9]{32}$/i);
const ActionIndexSchema = z.string().regex(/^(0|[1-9]\d{0,2})$/);
const UpdateActionSchema = z.object({
  description: z.string().trim().min(1).max(2_000),
  assignee: z.string().trim().max(300).nullable(),
  deadline_text: z.string().trim().max(300).nullable(),
  deadline: z.string().date().nullable(),
});

export async function PUT(request: Request, context: { params: Promise<{ jobId: string; actionIndex: string }> }) {
  const requestLog = startRequestLog("/api/asr/jobs/[jobId]/actions/[actionIndex]");
  const { jobId, actionIndex } = await context.params;
  const body = UpdateActionSchema.safeParse(await request.json().catch(() => null));
  if (!JobIdSchema.safeParse(jobId).success || !ActionIndexSchema.safeParse(actionIndex).success || !body.success) {
    return jsonWithRequestLog(requestLog, { error: "Проверьте поля поручения." }, { status: 400, outcome: "validation_error" });
  }

  try {
    const response = await fetch(getLocalAsrUrl(`/jobs/${jobId}/actions/${actionIndex}`), {
      method: "PUT",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body.data),
      signal: AbortSignal.timeout(10_000),
    });
    const payload: unknown = await response.json().catch(() => null);
    if (!response.ok) {
      const error = response.status === 404
        ? "Задание или поручение не найдены."
        : response.status === 409
          ? "Сначала сформируйте протокол."
          : response.status === 400
            ? "Поручение не прошло проверку."
            : "Не удалось сохранить поручение.";
      return jsonWithRequestLog(requestLog, { error }, { status: response.status === 400 || response.status === 404 || response.status === 409 ? response.status : 503, outcome: "upstream_error" });
    }
    return jsonWithRequestLog(requestLog, payload, { outcome: "success" });
  } catch {
    return jsonWithRequestLog(requestLog, { error: "Локальный ASR-сервис не запущен." }, { status: 503, outcome: "upstream_unavailable" });
  }
}
