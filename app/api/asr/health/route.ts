import { jsonWithRequestLog, startRequestLog } from "@/lib/request-log";
import { getLocalAsrUrl } from "@/lib/local-asr";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  const requestLog = startRequestLog("/api/asr/health");

  try {
    const response = await fetch(getLocalAsrUrl("/health"), {
      cache: "no-store",
      signal: AbortSignal.timeout(3_000),
    });
    const body: unknown = await response.json().catch(() => null);

    if (!response.ok) {
      return jsonWithRequestLog(
        requestLog,
        { status: "unavailable", error: "Локальный ASR-сервис ответил с ошибкой." },
        { status: 503, outcome: "upstream_error" },
      );
    }

    return jsonWithRequestLog(requestLog, body, { outcome: "success" });
  } catch {
    return jsonWithRequestLog(
      requestLog,
      { status: "unavailable", error: "Локальный ASR-сервис не запущен." },
      { status: 503, outcome: "upstream_unavailable" },
    );
  }
}
