import { format, parseISO, subDays } from "date-fns";
import { CalendarIcon } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { DateRange } from "react-day-picker";
import { dateFnsLocale } from "../../lib/format";
import { cn } from "../../lib/utils";
import { Button } from "./button";
import { Calendar } from "./calendar";
import { Popover, PopoverContent, PopoverTrigger } from "./popover";

type Props = {
  /** Datas em YYYY-MM-DD (contrato da API). */
  start: string;
  end: string;
  onChange: (start: string, end: string) => void;
  className?: string;
};

// Chaves em escopo de módulo, texto no render (troca de idioma ao vivo).
const PRESETS: { labelKey: string; days: number }[] = [
  { labelKey: "common:dateRange.days7", days: 7 },
  { labelKey: "common:dateRange.days30", days: 30 },
  { labelKey: "common:dateRange.days90", days: 90 },
  { labelKey: "common:dateRange.months12", days: 365 },
];

function toIso(d: Date): string {
  return format(d, "yyyy-MM-dd");
}

/** Seletor de período no idioma do app — substitui o input date nativo,
 * cujo formato de exibição segue o locale do browser, não o do app. */
export function DateRangePicker({ start, end, onChange, className }: Props) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<DateRange | undefined>();

  const startDate = parseISO(start);
  const endDate = parseISO(end);
  const dateFormat = t("common:dateFormat.short");
  const label = `${format(startDate, dateFormat, { locale: dateFnsLocale() })} – ${format(endDate, dateFormat, { locale: dateFnsLocale() })}`;

  const applyPreset = (days: number) => {
    const to = new Date();
    onChange(toIso(subDays(to, days - 1)), toIso(to));
    setOpen(false);
  };

  const handleSelect = (range: DateRange | undefined) => {
    setDraft(range);
    if (range?.from && range?.to) {
      onChange(toIso(range.from), toIso(range.to));
      setOpen(false);
      setDraft(undefined);
    }
  };

  return (
    <Popover
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (!o) setDraft(undefined);
      }}
    >
      <PopoverTrigger asChild>
        <Button variant="secondary" className={cn("font-mono text-xs font-normal tabular-nums", className)}>
          <CalendarIcon className="text-accent" />
          {label}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-auto p-0">
        <div className="flex">
          <div className="flex flex-col gap-1 border-r border-border p-2">
            {PRESETS.map((p) => (
              <Button key={p.days} variant="ghost" size="sm" className="justify-start" onClick={() => applyPreset(p.days)}>
                {t(p.labelKey)}
              </Button>
            ))}
          </div>
          <Calendar
            mode="range"
            numberOfMonths={2}
            defaultMonth={subDays(endDate, 31)}
            selected={draft ?? { from: startDate, to: endDate }}
            onSelect={handleSelect}
            disabled={{ after: new Date() }}
          />
        </div>
      </PopoverContent>
    </Popover>
  );
}
