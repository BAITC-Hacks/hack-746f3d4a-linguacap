import { getLocalAsrUrl } from "@/lib/local-asr";
import { jsonWithRequestLog, startRequestLog } from "@/lib/request-log";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const MAX_UPLOAD_BYTES = 1_073_741_824;

export async function POST(request: Request) {
  const requestLog = startRequestLog("/api/asr/transcribe");

  try {
    const incoming = await request.formData();
    const file = incoming.get("file");
    if (!(file instanceof File)) {
      return jsonWithRequestLog(requestLog, { error: "Выберите аудиофайл." }, { status: 400, outcome: "validation_error" });
    }
    if (file.size === 0 || file.size > MAX_UPLOAD_BYTES) {
      return jsonWithRequestLog(requestLog, { error: "Размер файла должен быть от 1 байта до 1 GiB." }, { status: 400, outcome: "validation_error" });
    }

    const formData = new FormData();
    formData.set("file", file, file.name);
    const response = await fetch(getLocalAsrUrl("/transcribe"), {
      method: "POST",
      body: formData,
      cache: "no-store",
      signal: AbortSignal.timeout(15_000),
    });
    const payload: unknown = await response.json().catch(() => null);

    if (!response.ok) {
      return jsonWithRequestLog(
        requestLog,
        { error: "Локальный ASR-сервис не принял запись." },
        { status: response.status === 400 ? 400 : 503, outcome: "upstream_error" },
      );
    }
    return jsonWithRequestLog(requestLog, payload, { status: 202, outcome: "success" });
  } catch {
    return jsonWithRequestLog(
      requestLog,
      { error: "Локальный ASR-сервис не запущен или недоступен." },
      { status: 503, outcome: "upstream_unavailable" },
    );
  }
}
