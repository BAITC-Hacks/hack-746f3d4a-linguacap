import { z } from "zod";

import { getLocalAsrUrl } from "@/lib/local-asr";
import { jsonWithRequestLog, startRequestLog } from "@/lib/request-log";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const JobIdSchema = z.string().regex(/^[a-f0-9]{32}$/i);
const SegmentIdSchema = z.string().regex(/^[a-z0-9][a-z0-9_-]{0,99}$/i);
const UpdateSegmentSchema = z.object({ text: z.string().trim().min(1).max(10_000) });

export async function PUT(request: Request, context: { params: Promise<{ jobId: string; segmentId: string }> }) {
  const requestLog = startRequestLog("/api/asr/jobs/[jobId]/segments/[segmentId]");
  const { jobId, segmentId } = await context.params;
  const body = UpdateSegmentSchema.safeParse(await request.json().catch(() => null));
  if (!JobIdSchema.safeParse(jobId).success || !SegmentIdSchema.safeParse(segmentId).success || !body.success) {
    return jsonWithRequestLog(requestLog, { error: "Проверьте текст и идентификатор реплики." }, { status: 400, outcome: "validation_error" });
  }

  try {
    const response = await fetch(getLocalAsrUrl(`/jobs/${jobId}/segments/${segmentId}`), {
      method: "PUT",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body.data),
      signal: AbortSignal.timeout(10_000),
    });
    const payload: unknown = await response.json().catch(() => null);
    if (!response.ok) {
      const error = response.status === 404
        ? "Задание или реплика не найдены."
        : response.status === 409
          ? "Расшифровка ещё не готова."
          : response.status === 400
            ? "Текст реплики не прошёл проверку."
            : "Не удалось сохранить реплику.";
      return jsonWithRequestLog(requestLog, { error }, { status: response.status === 400 || response.status === 404 || response.status === 409 ? response.status : 503, outcome: "upstream_error" });
    }
    return jsonWithRequestLog(requestLog, payload, { outcome: "success" });
  } catch {
    return jsonWithRequestLog(requestLog, { error: "Локальный ASR-сервис не запущен." }, { status: 503, outcome: "upstream_unavailable" });
  }
}
