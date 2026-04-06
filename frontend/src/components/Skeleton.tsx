type Props = {
  variant?: "text" | "title" | "card" | "chart" | "row";
  width?: string;
  className?: string;
};

const HEIGHT_MAP: Record<string, string> = {
  text: "14px",
  title: "20px",
  card: "80px",
  chart: "140px",
  row: "36px",
};

const WIDTH_MAP: Record<string, string> = {
  text: "60%",
  title: "40%",
  card: "100%",
  chart: "100%",
  row: "100%",
};

export function Skeleton({ variant = "text", width, className }: Props) {
  return (
    <div
      className={`skeleton skeleton-${variant}${className ? ` ${className}` : ""}`}
      style={{
        height: HEIGHT_MAP[variant],
        width: width ?? WIDTH_MAP[variant],
      }}
    />
  );
}
