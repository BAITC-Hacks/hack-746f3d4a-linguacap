"use client";

import Link from "next/link";
import { ChevronRight, FlaskConical, Layers3 } from "lucide-react";
import { useState } from "react";

import { AILoading } from "@/components/ai/ai-loading";
import { AIResult } from "@/components/ai/ai-result";
import { ExamplePrompts } from "@/components/ai/example-prompts";
import { PromptInput } from "@/components/ai/prompt-input";
import { ThemeToggle } from "@/components/ai/theme-toggle";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import type { AIResult as AIResultType, RequestMode } from "@/types/ai";

type AIWorkspaceProps = {
  activePage: "home" | "demo";
  description: string;
  examples: string[];
  title: string;
};

type ErrorPayload = { error?: unknown };

function isErrorPayload(payload: unknown): payload is ErrorPayload {
  return typeof payload === "object" && payload !== null;
}

export function AIWorkspace({ activePage, description, examples, title }: AIWorkspaceProps) {
  const [message, setMessage] = useState("");
  const [result, setResult] = useState<AIResultType>();
  const [error, setError] = useState<string>();
  const [pendingMode, setPendingMode] = useState<RequestMode>();

  const runRequest = async (mode: RequestMode) => {
    const trimmedMessage = message.trim();
    if (!trimmedMessage || pendingMode) return;

    setPendingMode(mode);
    setError(undefined);
    setResult(undefined);

    try {
      const response = await fetch(mode === "analyze" ? "/api/analyze" : "/api/ai", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: trimmedMessage }),
      });
      const payload: unknown = await response.json().catch(() => null);

      if (!response.ok) {
        const messageFromServer = isErrorPayload(payload) && typeof payload.error === "string" ? payload.error : "The request could not be completed. Please try again.";
        setError(messageFromServer);
        return;
      }

      if (mode === "ask" && isErrorPayload(payload) && typeof (payload as { result?: unknown }).result === "string") {
        setResult({ kind: "text", content: (payload as { result: string }).result });
        return;
      }

      if (
        mode === "analyze" &&
        isErrorPayload(payload) &&
        typeof (payload as { title?: unknown }).title === "string" &&
        typeof (payload as { summary?: unknown }).summary === "string" &&
        typeof (payload as { score?: unknown }).score === "number" &&
        Array.isArray((payload as { recommendations?: unknown }).recommendations) &&
        (payload as { recommendations: unknown[] }).recommendations.every((item) => typeof item === "string")
      ) {
        const analysis = payload as { title: string; summary: string; score: number; recommendations: string[] };
        setResult({ kind: "analysis", content: analysis });
        return;
      }

      setError("The server returned an unexpected response. Please try again.");
    } catch {
      setError("Network connection failed. Check your connection and try again.");
    } finally {
      setPendingMode(undefined);
    }
  };

  const chooseExample = (example: string) => {
    if (pendingMode) return;
    setMessage(example);
    setError(undefined);
  };

  return (
    <main className="min-h-screen px-4 py-4 sm:px-6 sm:py-6 lg:px-8">
      <div className="mx-auto max-w-6xl">
        <header className="mb-8 flex items-center justify-between gap-4 sm:mb-12">
          <Link className="group flex items-center gap-2" href="/">
            <span className="bg-accent flex h-9 w-9 items-center justify-center rounded-xl shadow-glow">
              <Layers3 aria-hidden="true" className="h-4 w-4 text-white dark:text-slate-950" />
            </span>
            <span className="text-base font-semibold tracking-tight">Launchpad AI</span>
          </Link>
          <div className="flex items-center gap-1 sm:gap-2">
            <Link
              aria-current={activePage === "home" ? "page" : undefined}
              className={`rounded-lg px-3 py-2 text-sm transition ${activePage === "home" ? "bg-[rgb(var(--accent-soft))] font-medium text-[rgb(var(--foreground))]" : "text-muted hover:bg-[rgb(var(--accent-soft))] hover:text-[rgb(var(--foreground))]"}`}
              href="/"
            >
              Workspace
            </Link>
            <Link
              aria-current={activePage === "demo" ? "page" : undefined}
              className={`rounded-lg px-3 py-2 text-sm transition ${activePage === "demo" ? "bg-[rgb(var(--accent-soft))] font-medium text-[rgb(var(--foreground))]" : "text-muted hover:bg-[rgb(var(--accent-soft))] hover:text-[rgb(var(--foreground))]"}`}
              href="/demo"
            >
              Demo
            </Link>
            <ThemeToggle />
          </div>
        </header>

        <section className="mb-8 max-w-3xl sm:mb-10">
          <div className="mb-3 flex items-center gap-2 text-sm font-medium text-accent">
            <span className="h-2 w-2 rounded-full bg-accent" />
            Устаревший экран — локальная обработка готовится
          </div>
          <h1 className="text-3xl font-semibold tracking-[-0.04em] sm:text-5xl">{title}</h1>
          <p className="mt-4 max-w-2xl text-base leading-7 text-muted sm:text-lg">{description}</p>
        </section>

        <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(340px,0.82fr)]">
          <Card className="p-4 sm:p-6">
            <PromptInput disabled={Boolean(pendingMode)} onChange={setMessage} onSubmit={() => runRequest("ask")} value={message} />
            <div className="mt-6 border-t pt-5">
              <ExamplePrompts disabled={Boolean(pendingMode)} onSelect={chooseExample} prompts={examples} />
            </div>
          </Card>

          <section aria-live="polite" aria-label="AI result" className="min-h-48">
            {pendingMode ? <Card><AILoading structured={pendingMode === "analyze"} /></Card> : <AIResult error={error} result={result} />}
          </section>
        </div>

        <section className="mt-6 flex flex-col gap-3 rounded-2xl border bg-[rgb(var(--accent-soft))] px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-3">
            <FlaskConical aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-accent" />
            <div>
              <p className="font-medium">Need a judge-ready analysis?</p>
              <p className="mt-1 text-sm leading-6 text-muted">Use a structured response to turn an idea into a title, score, and next moves.</p>
            </div>
          </div>
          <Button disabled={Boolean(pendingMode) || !message.trim()} onClick={() => runRequest("analyze")} variant="secondary">
            Analyze idea
            <ChevronRight aria-hidden="true" className="h-4 w-4" />
          </Button>
        </section>

        <footer className="flex flex-col gap-2 py-10 text-xs text-muted sm:flex-row sm:items-center sm:justify-between">
          <span>No sign-in. No database. Your API key stays on the server.</span>
          <span>Cmd/Ctrl + Enter to send</span>
        </footer>
      </div>
    </main>
  );
}
