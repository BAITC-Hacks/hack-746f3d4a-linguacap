import { ArrowUpRight, CheckCircle2, Lightbulb } from "lucide-react";

import type { AIResult as AIResultType } from "@/types/ai";

import { Card } from "@/components/ui/card";

type AIResultProps = {
  error?: string;
  result?: AIResultType;
};

export function AIResult({ error, result }: AIResultProps) {
  if (error) {
    return (
      <Card className="border-rose-300 bg-rose-50 p-5 text-rose-950 dark:border-rose-900 dark:bg-rose-950/30 dark:text-rose-100">
        <p className="font-semibold">Couldn’t complete that request</p>
        <p className="mt-1 text-sm leading-6 opacity-85">{error}</p>
      </Card>
    );
  }

  if (!result) {
    return (
      <Card className="surface-raised flex min-h-48 flex-col justify-center p-6">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[rgb(var(--accent-soft))]">
          <ArrowUpRight aria-hidden="true" className="h-5 w-5 text-accent" />
        </div>
        <p className="mt-4 font-semibold">Ready when you are</p>
        <p className="mt-1 max-w-md text-sm leading-6 text-muted">Start with a question, a product idea, or a piece of text you want to improve.</p>
      </Card>
    );
  }

  if (result.kind === "text") {
    return (
      <Card className="overflow-hidden">
        <div className="flex items-center gap-2 border-b px-5 py-3">
          <CheckCircle2 aria-hidden="true" className="h-4 w-4 text-accent" />
          <p className="text-sm font-medium">Response</p>
        </div>
        <div className="whitespace-pre-wrap px-5 py-5 text-[0.98rem] leading-7 text-[rgb(var(--foreground))]">{result.content}</div>
      </Card>
    );
  }

  const { content } = result;

  return (
    <Card className="overflow-hidden">
      <div className="flex items-start justify-between gap-4 border-b px-5 py-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-accent">Structured analysis</p>
          <h2 className="mt-1 text-lg font-semibold tracking-tight">{content.title}</h2>
        </div>
        <div className="rounded-xl bg-[rgb(var(--accent-soft))] px-3 py-2 text-right">
          <p className="text-xl font-bold text-accent">{Math.round(content.score)}</p>
          <p className="text-xs text-muted">opportunity score</p>
        </div>
      </div>
      <div className="space-y-5 px-5 py-5">
        <p className="text-[0.98rem] leading-7 text-[rgb(var(--foreground))]">{content.summary}</p>
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold">
            <Lightbulb aria-hidden="true" className="h-4 w-4 text-accent" />
            Recommended next moves
          </div>
          <ul className="mt-3 space-y-2">
            {content.recommendations.map((recommendation) => (
              <li className="flex gap-3 text-sm leading-6 text-muted" key={recommendation}>
                <span aria-hidden="true" className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
                {recommendation}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </Card>
  );
}
