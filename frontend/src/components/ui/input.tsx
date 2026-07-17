import * as React from "react";
import { cn } from "../../lib/utils";

const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type, ...props }, ref) => (
    <input
      ref={ref}
      type={type}
      className={cn(
        "flex h-9 w-full rounded-md border border-input bg-panel px-3 py-1 text-sm text-foreground",
        "placeholder:text-tertiary",
        "transition-[border-color,box-shadow] duration-150",
        "hover:border-border-strong",
        "shadow-none focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent-soft",
        "disabled:cursor-not-allowed disabled:opacity-50",
        "file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground",
        className
      )}
      {...props}
    />
  )
);
Input.displayName = "Input";

const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => (
    <textarea
      ref={ref}
      className={cn(
        "flex min-h-[72px] w-full rounded-md border border-input bg-panel px-3 py-2 text-sm text-foreground",
        "placeholder:text-tertiary",
        "transition-[border-color,box-shadow] duration-150",
        "hover:border-border-strong",
        "shadow-none focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent-soft",
        "disabled:cursor-not-allowed disabled:opacity-50",
        className
      )}
      {...props}
    />
  )
);
Textarea.displayName = "Textarea";

export { Input, Textarea };
