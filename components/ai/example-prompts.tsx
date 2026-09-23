import { ArrowUpRight } from "lucide-react";

import { Button } from "@/components/ui/button";

type ExamplePromptsProps = {
  prompts: string[];
  onSelect: (prompt: string) => void;
  disabled?: boolean;
};

export function ExamplePrompts({ prompts, onSelect, disabled }: ExamplePromptsProps) {
  return (
    <div>
      <p className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-muted">Try a starting point</p>
      <div className="flex flex-wrap gap-2">
        {prompts.map((prompt) => (
          <Button
            className="h-auto min-h-0 max-w-full justify-between px-3 py-2 text-left text-xs leading-5"
            disabled={disabled}
            key={prompt}
            onClick={() => onSelect(prompt)}
            variant="secondary"
          >
            <span className="line-clamp-1">{prompt}</span>
            <ArrowUpRight aria-hidden="true" className="h-3.5 w-3.5 shrink-0" />
          </Button>
        ))}
      </div>
    </div>
  );
}
