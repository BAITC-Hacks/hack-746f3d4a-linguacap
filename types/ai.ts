import type { Analysis } from "@/lib/schemas";

export type AIResult =
  | { kind: "text"; content: string }
  | { kind: "analysis"; content: Analysis };

export type RequestMode = "ask" | "analyze";
