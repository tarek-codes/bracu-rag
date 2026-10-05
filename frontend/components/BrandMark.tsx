export function BrandMark({ size = 32 }: { size?: number }) {
  return (
    <span
      aria-hidden
      className="inline-flex shrink-0 items-center justify-center rounded-[10px] bg-accent font-heading font-semibold text-accent-fg"
      style={{ width: size, height: size, fontSize: size * 0.36, letterSpacing: "-0.02em" }}
    >
      BU
    </span>
  );
}
