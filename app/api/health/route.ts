import { jsonWithRequestLog, startRequestLog } from "@/lib/request-log";

export const runtime = "nodejs";

export function GET() {
  return jsonWithRequestLog(startRequestLog("/api/health"), { status: "ok" }, { outcome: "success" });
}
