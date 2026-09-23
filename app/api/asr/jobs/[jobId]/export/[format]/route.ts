import { z } from "zod";

import { getLocalAsrUrl } from "@/lib/local-asr";
import { fileWithRequestLog, jsonWithRequestLog, startRequestLog } from "@/lib/request-log";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const JobIdSchema = z.string().regex(/^[a-f0-9]{32}$/i);
const ExportFormatSchema = z.enum(["docx", "pdf"]);

export async function GET(_request: Request, context: { params: Promise<{ jobId: string; format: string }> }) {
  const requestLog = startRequestLog("/api/asr/jobs/[jobId]/export/[format]");
  const { jobId, format } = await context.params;
  if (!JobIdSchema.safeParse(jobId).success || !ExportFormatSchema.safeParse(format).success) {
    return jsonWithRequestLog(requestLog, { error: "Некорректный запрос экспорта." }, { status: 400, outcome: "validation_error" });
  }

  try {
    const response = await fetch(getLocalAsrUrl(`/jobs/${jobId}/export/${format}`), {
      cache: "no-store",
      signal: AbortSignal.timeout(30_000),
    });
    if (!response.ok) {
      const error = response.status === 404
        ? "Задание не найдено."
        : response.status === 409
          ? "Сначала сформируйте саммари и поручения."
          : response.status === 503
            ? "Локальный экспорт недоступен."
            : "Не удалось сформировать файл.";
      return jsonWithRequestLog(requestLog, { error }, { status: response.status === 404 || response.status === 409 ? response.status : 503, outcome: "upstream_error" });
    }
    return fileWithRequestLog(
      requestLog,
      response.body,
      {
        "Content-Type": response.headers.get("content-type") ?? "application/octet-stream",
        "Content-Disposition": response.headers.get("content-disposition") ?? `attachment; filename="protocol.${format}"`,
      },
    );
  } catch {
    return jsonWithRequestLog(requestLog, { error: "Локальный ASR-сервис не запущен." }, { status: 503, outcome: "upstream_unavailable" });
  }
}
