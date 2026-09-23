type LogOutcome = "success" | "validation_error" | "upstream_error" | "upstream_unavailable" | "empty_response" | "disabled";

type RequestLog = {
  requestId: string;
  route: string;
  startedAt: number;
};

type ResponseOptions = {
  outcome: LogOutcome;
  status?: number;
};

export function startRequestLog(route: string): RequestLog {
  return {
    requestId: crypto.randomUUID(),
    route,
    startedAt: performance.now(),
  };
}

export function jsonWithRequestLog<T>(requestLog: RequestLog, payload: T, { outcome, status = 200 }: ResponseOptions) {
  writeRequestLog(requestLog, outcome, status);
  return Response.json(payload, {
    status,
    headers: {
      "X-Request-Id": requestLog.requestId,
    },
  });
}

export function fileWithRequestLog(requestLog: RequestLog, body: BodyInit | null, headers: HeadersInit, status = 200) {
  writeRequestLog(requestLog, "success", status);
  const responseHeaders = new Headers(headers);
  responseHeaders.set("X-Request-Id", requestLog.requestId);
  return new Response(body, { status, headers: responseHeaders });
}

function writeRequestLog(requestLog: RequestLog, outcome: LogOutcome, status: number) {
  const durationMs = Math.round(performance.now() - requestLog.startedAt);
  const entry = JSON.stringify({
    timestamp: new Date().toISOString(),
    level: outcome === "success" ? "info" : "warn",
    event: "api.request",
    requestId: requestLog.requestId,
    route: requestLog.route,
    status,
    durationMs,
    outcome,
  });

  if (outcome === "success") {
    console.info(entry);
  } else {
    console.warn(entry);
  }
}
