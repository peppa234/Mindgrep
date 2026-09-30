/** Tiled feTurbulence grain. At 3% it is invisible as texture but breaks up gradient banding. */
export function NoiseOverlay({
  opacity = 0.03,
  fixed = false,
  className = "",
}: {
  opacity?: number;
  fixed?: boolean;
  className?: string;
}) {
  return <div aria-hidden className={`noise-overlay ${fixed ? "fixed" : "absolute"} inset-0 ${className}`} style={{ opacity }} />;
}
