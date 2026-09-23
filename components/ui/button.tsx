import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import type { ButtonHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 rounded-xl font-medium transition duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-[rgb(var(--background))] disabled:cursor-not-allowed disabled:opacity-50",
  {
    variants: {
      variant: {
        primary: "bg-accent px-4 text-white hover:brightness-95 dark:text-slate-950",
        secondary: "surface-raised border px-4 text-[rgb(var(--foreground))] hover:bg-[rgb(var(--accent-soft))]",
        ghost: "text-muted hover:bg-[rgb(var(--accent-soft))] hover:text-[rgb(var(--foreground))]",
      },
      size: {
        default: "min-h-11 text-sm",
        sm: "min-h-9 rounded-lg px-3 text-sm",
        icon: "h-10 w-10 rounded-lg p-0",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "default",
    },
  },
);

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & VariantProps<typeof buttonVariants> & { asChild?: boolean };

export function Button({ className, variant, size, asChild = false, type = "button", ...props }: ButtonProps) {
  const Component = asChild ? Slot : "button";

  return (
    <Component
      className={cn(buttonVariants({ variant, size, className }))}
      type={type}
      {...props}
    />
  );
}
