import { Segmented } from "@/components/ui/segmented";
import type { TrafficRange } from "@/lib/types";

const RANGES: { value: TrafficRange; label: string }[] = [
  { value: "24h", label: "24 h" },
  { value: "7d", label: "7 días" },
  { value: "30d", label: "30 días" },
  { value: "1y", label: "1 año" },
];

export function RangeSelector({
  value, onChange, size,
}: { value: TrafficRange; onChange: (range: TrafficRange) => void; size?: "sm" | "default" }) {
  return <Segmented value={value} onChange={onChange} options={RANGES} size={size} />;
}
