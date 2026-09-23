import { jsonWithRequestLog, startRequestLog } from "@/lib/request-log";

export const runtime = "nodejs";

export function POST() {
  const requestLog = startRequestLog("/api/ai");
  return jsonWithRequestLog(
    requestLog,
    { error: "Внешний AI-маршрут отключён: обработка совещаний выполняется только локально." },
    { status: 410, outcome: "disabled" },
  );
}
