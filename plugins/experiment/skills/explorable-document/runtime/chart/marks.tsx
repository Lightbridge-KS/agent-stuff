export function SeriesMark({
  index,
  x,
  y,
  selected = false,
}: {
  index: number;
  x: number;
  y: number;
  selected?: boolean;
}) {
  const r = selected ? 6 : 4;
  const common = {
    fill: "var(--panel)",
    stroke: "currentColor",
    strokeWidth: selected ? 3 : 2,
  };
  if (index % 4 === 1)
    return (
      <rect {...common} x={x - r} y={y - r} width={r * 2} height={r * 2} />
    );
  if (index % 4 === 2)
    return (
      <path
        {...common}
        d={`M ${x} ${y - r - 1} L ${x + r + 1} ${y} L ${x} ${y + r + 1} L ${x - r - 1} ${y} Z`}
      />
    );
  if (index % 4 === 3)
    return (
      <path
        {...common}
        d={`M ${x} ${y - r - 1} L ${x + r + 1} ${y + r} L ${x - r - 1} ${y + r} Z`}
      />
    );
  return <circle {...common} cx={x} cy={y} r={r} />;
}
export const dashFor = (index: number): string | undefined =>
  [undefined, "7 5", "2 4", "9 3 2 3"][index % 4];
