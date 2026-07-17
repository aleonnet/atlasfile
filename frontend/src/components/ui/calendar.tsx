import { ChevronLeft, ChevronRight } from "lucide-react";
import { DayPicker, type DayPickerProps } from "react-day-picker";
import { ptBR } from "react-day-picker/locale";
import { cn } from "../../lib/utils";

/**
 * Calendário da marca sobre react-day-picker v10 (headless, estilizado 100%
 * via classNames → tokens). Locale fixo pt-BR — o app é PT-BR por contrato.
 */
export function Calendar({ className, classNames, ...props }: DayPickerProps) {
  return (
    <DayPicker
      locale={ptBR}
      showOutsideDays
      className={cn("select-none p-3", className)}
      classNames={{
        months: "relative flex flex-col gap-4 sm:flex-row",
        month: "flex w-full flex-col gap-3",
        nav: "absolute inset-x-0 top-0 flex items-center justify-between",
        button_previous:
          "inline-flex size-7 items-center justify-center rounded-md border-0 bg-transparent text-muted-foreground transition-colors hover:bg-accent-soft hover:text-foreground disabled:pointer-events-none disabled:opacity-40",
        button_next:
          "inline-flex size-7 items-center justify-center rounded-md border-0 bg-transparent text-muted-foreground transition-colors hover:bg-accent-soft hover:text-foreground disabled:pointer-events-none disabled:opacity-40",
        month_caption: "flex h-7 items-center justify-center",
        caption_label: "font-display text-sm font-semibold capitalize text-foreground-strong",
        month_grid: "w-full border-collapse",
        weekdays: "flex",
        weekday: "w-9 pb-1 font-mono text-[0.65rem] font-normal uppercase text-tertiary",
        week: "mt-0.5 flex w-full",
        day: "relative size-9 p-0 text-center text-sm",
        day_button: cn(
          "inline-flex size-9 items-center justify-center rounded-md border-0 bg-transparent font-mono text-[0.8rem] text-foreground",
          "transition-colors hover:bg-accent-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        ),
        range_start: "rounded-l-md bg-accent-soft [&>button]:bg-primary [&>button]:text-primary-foreground [&>button]:hover:bg-accent-light",
        range_end: "rounded-r-md bg-accent-soft [&>button]:bg-primary [&>button]:text-primary-foreground [&>button]:hover:bg-accent-light",
        range_middle: "bg-accent-soft [&>button]:rounded-none",
        selected: "[&>button]:bg-primary [&>button]:text-primary-foreground",
        today: "[&>button]:font-bold [&>button]:text-accent",
        outside: "[&>button]:text-tertiary [&>button]:opacity-50",
        disabled: "[&>button]:pointer-events-none [&>button]:opacity-30",
        hidden: "invisible",
        ...classNames,
      }}
      components={{
        Chevron: ({ orientation, ...rest }) =>
          orientation === "left" ? <ChevronLeft className="size-4" {...rest} /> : <ChevronRight className="size-4" {...rest} />,
      }}
      {...props}
    />
  );
}
