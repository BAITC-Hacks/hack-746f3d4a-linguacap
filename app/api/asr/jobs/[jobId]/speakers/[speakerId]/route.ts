import { z } from "zod";

import { getLocalAsrUrl } from "@/lib/local-asr";
import { jsonWithRequestLog, startRequestLog } from "@/lib/request-log";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const JobIdSchema = z.string().regex(/^[a-f0-9]{32}$/i);
const SpeakerIdSchema = z.string().regex(/^SPEAKER_\d{2}$/);
const RenameRequestSchema = z.object({ display_name: z.string().trim().min(1).max(100) });

export async function POST(request: Request, context: { params: Promise<{ jobId: string; speakerId: string }> }) {
  const requestLog = startRequestLog("/api/asr/jobs/[jobId]/speakers/[speakerId]");
  const { jobId, speakerId } = await context.params;
  const body = RenameRequestSchema.safeParse(await request.json().catch(() => null));
  if (!JobIdSchema.safeParse(jobId).success || !SpeakerIdSchema.safeParse(speakerId).success || !body.success) {
    return jsonWithRequestLog(requestLog, { error: "Проверьте идентификатор и новое имя спикера." }, { status: 400, outcome: "validation_error" });
  }

  try {
    const response = await fetch(getLocalAsrUrl(`/jobs/${jobId}/speakers/${speakerId}`), {
      method: "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body.data),
      signal: AbortSignal.timeout(3_000),
    });
    const payload: unknown = await response.json().catch(() => null);
    if (!response.ok) {
      return jsonWithRequestLog(
        requestLog,
        { error: response.status === 404 ? "Задание или спикер не найден." : "Не удалось переименовать спикера." },
        { status: response.status === 404 ? 404 : response.status === 409 ? 409 : 503, outcome: "upstream_error" },
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
