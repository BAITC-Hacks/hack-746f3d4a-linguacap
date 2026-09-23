"use client";

import { Sparkles } from "lucide-react";
import { useEffect, useState } from "react";

const MESSAGES = ["Thinking through it…", "Shaping a useful response…", "Checking the details…"];

export function AILoading({ structured = false }: { structured?: boolean }) {
  const [messageIndex, setMessageIndex] = useState(0);

  useEffect(() => {
    const interval = window.setInterval(() => {
      setMessageIndex((current) => (current + 1) % MESSAGES.length);
    }, 1_600);

    return () => window.clearInterval(interval);
  }, []);

  return (
    <div aria-live="polite" className="flex min-h-48 flex-col items-center justify-center gap-4 px-6 py-10 text-center">
      <div className="bg-accent-soft flex h-12 w-12 items-center justify-center rounded-2xl">
        <Sparkles aria-hidden="true" className="animate-soft-pulse h-5 w-5 text-accent" />
      </div>
      <div>
        <p className="font-medium text-[rgb(var(--foreground))]">{structured ? "Analyzing your idea…" : MESSAGES[messageIndex]}</p>
        <p className="mt-1 text-sm text-muted">This usually takes just a moment.</p>
      </div>
    </div>
  );
}
