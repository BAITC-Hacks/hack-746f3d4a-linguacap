import { jsonWithRequestLog, startRequestLog } from "@/lib/request-log";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const LOCAL_HOSTS = new Set(["127.0.0.1", "localhost", "::1"]);

function getLocalAsrHealthUrl() {
  const configuredUrl = process.env.ASR_SERVICE_URL ?? "http://127.0.0.1:8000";
  const serviceUrl = new URL(configuredUrl);

  if (!LOCAL_HOSTS.has(serviceUrl.hostname)) {
    throw new Error("ASR_SERVICE_URL must point to a local service.");
  }

  return new URL("/health", serviceUrl);
}

export async function GET() {
  const requestLog = startRequestLog("/api/asr/health");

  try {
    const response = await fetch(getLocalAsrHealthUrl(), {
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
