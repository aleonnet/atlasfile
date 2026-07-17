import { format, parseISO, subDays } from "date-fns";
import { ptBR } from "date-fns/locale";
import { CalendarIcon } from "lucide-react";
import { useState } from "react";
import type { DateRange } from "react-day-picker";
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

const PRESETS: { label: string; days: number }[] = [
  { label: "7 dias", days: 7 },
  { label: "30 dias", days: 30 },
  { label: "90 dias", days: 90 },
  { label: "12 meses", days: 365 },
];

function toIso(d: Date): string {
  return format(d, "yyyy-MM-dd");
}

/** Seletor de período pt-BR (dd/MM/yyyy) — substitui o input date nativo,
 * cujo formato de exibição segue o locale do browser, não o do app. */
export function DateRangePicker({ start, end, onChange, className }: Props) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<DateRange | undefined>();

  const startDate = parseISO(start);
  const endDate = parseISO(end);
  const label = `${format(startDate, "dd/MM/yyyy", { locale: ptBR })} – ${format(endDate, "dd/MM/yyyy", { locale: ptBR })}`;

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
                {p.label}
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
