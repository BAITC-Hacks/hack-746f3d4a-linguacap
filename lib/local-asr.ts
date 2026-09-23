const LOCAL_HOSTS = new Set(["127.0.0.1", "localhost", "::1"]);

export function getLocalAsrServiceUrl(): URL {
  const configuredUrl = process.env.ASR_SERVICE_URL ?? "http://127.0.0.1:8000";
  const serviceUrl = new URL(configuredUrl);

  if (!LOCAL_HOSTS.has(serviceUrl.hostname)) {
    throw new Error("ASR_SERVICE_URL must point to a local service.");
  }

  return serviceUrl;
}

export function getLocalAsrUrl(path: string): URL {
  return new URL(path, getLocalAsrServiceUrl());
}
