import { Button } from "@/components/ui/button";
import type { TrafficRange } from "@/lib/types";

const RANGES: { value: TrafficRange; label: string }[] = [
  { value: "24h", label: "24 horas" },
  { value: "7d", label: "7 días" },
  { value: "30d", label: "30 días" },
  { value: "1y", label: "1 año" },
];

interface RangeSelectorProps {
  value: TrafficRange;
  onChange: (range: TrafficRange) => void;
}

export function RangeSelector({ value, onChange }: RangeSelectorProps) {
  return (
    <div className="flex gap-1">
      {RANGES.map(r => (
        <Button
          key={r.value}
          variant={value === r.value ? "default" : "outline"}
          size="sm"
          onClick={() => onChange(r.value)}
        >
          {r.label}
        </Button>
      ))}
    </div>
  );
}
